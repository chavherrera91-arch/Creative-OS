"""WP-2.6 — resilient ingestion: retries, circuit breaker, idempotency."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantos.data.connectors import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
)
from quantos.data.ingest import CircuitBreaker, IngestionRunner, RetryPolicy, WatermarkStore
from quantos.data.schema import FieldSpec, Schema, SchemaRegistry
from quantos.data.store import DuckDBStore

SCHEMA = Schema(
    name="flaky",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("value", "float64"),
    ),
    primary_key=("symbol", "event_time"),
)


def make_rows(symbol: str, n: int = 6) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "event_time": times,
            "ingested_at": times,
            "value": [float(i) for i in range(n)],
        }
    )


class FlakyConnector(Connector):
    """Raises ``failures`` times, then serves a fixed frame."""

    metadata = ConnectorMetadata("flaky", "testing", "flaky", 3600)

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    def fetch(self, req: FetchRequest) -> FetchResult:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"boom #{self.calls}")
        return self.synthetic(req)

    def synthetic(self, req: FetchRequest) -> FetchResult:
        return FetchResult(rows=make_rows(req.symbol), schema_version=1, source_mode="synthetic")


@pytest.fixture()
def schemas() -> SchemaRegistry:
    reg = SchemaRegistry()
    reg.register(SCHEMA)
    return reg


def make_runner(
    schemas: SchemaRegistry, *, max_attempts: int = 4, breaker_threshold: int = 3
) -> tuple[IngestionRunner, DuckDBStore, list[float]]:
    store = DuckDBStore()
    sleeps: list[float] = []
    runner = IngestionRunner(
        store,
        retry=RetryPolicy(max_attempts=max_attempts, base_delay=0.5, jitter=True),
        schemas=schemas,
        breaker_threshold=breaker_threshold,
        sleep=sleeps.append,  # recorded, never actually slept
    )
    return runner, store, sleeps


class TestRetryPolicy:
    def test_backoff_grows_and_caps(self) -> None:
        policy = RetryPolicy(base_delay=1.0, max_delay=8.0, jitter=False)
        assert [policy.delay(a) for a in (1, 2, 3, 4, 5)] == [1.0, 2.0, 4.0, 8.0, 8.0]

    def test_jitter_is_bounded_and_seeded(self) -> None:
        policy = RetryPolicy(base_delay=2.0, jitter=True)
        delays = [policy.delay(1, np.random.default_rng(42)) for _ in range(50)]
        assert all(1.0 <= d <= 3.0 for d in delays)
        # same seed -> same jitter (I8)
        assert delays[0] == policy.delay(1, np.random.default_rng(42))

    def test_call_raises_last_error_after_exhaustion(self) -> None:
        policy = RetryPolicy(max_attempts=3, jitter=False)
        attempts: list[int] = []

        def always_fails() -> None:
            attempts.append(1)
            raise ValueError("nope")

        with pytest.raises(ValueError):
            policy.call(always_fails, sleep=lambda _s: None)
        assert len(attempts) == 3


class TestCircuitBreaker:
    def test_opens_blocks_and_recovers(self) -> None:
        clock = {"t": 0.0}
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=10.0, clock=lambda: clock["t"])
        assert breaker.state == "closed" and breaker.allow()
        breaker.record(False)
        assert breaker.allow()  # under threshold
        breaker.record(False)
        assert breaker.state == "open" and not breaker.allow()
        clock["t"] = 11.0  # cool-off elapsed -> half-open probe allowed
        assert breaker.state == "half_open" and breaker.allow()
        breaker.record(True)
        assert breaker.state == "closed"

    def test_half_open_failure_reopens(self) -> None:
        clock = {"t": 0.0}
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=5.0, clock=lambda: clock["t"])
        breaker.record(False)
        clock["t"] = 6.0
        assert breaker.allow()
        breaker.record(False)  # the probe failed
        assert breaker.state == "open" and not breaker.allow()


class TestRunner:
    def test_flaky_connector_is_retried_then_succeeds(self, schemas: SchemaRegistry) -> None:
        runner, store, sleeps = make_runner(schemas)
        connector = FlakyConnector(failures=2)
        report = runner.run(connector, FetchRequest(symbol="BTC/USDT"))
        assert report.ok
        assert connector.calls == 3  # 2 failures + 1 success, per policy
        assert len(sleeps) == 2 and all(s > 0 for s in sleeps)
        assert len(store.read("curated", "flaky")) == 6

    def test_exhausted_retries_fail_cleanly(self, schemas: SchemaRegistry) -> None:
        runner, store, _ = make_runner(schemas, max_attempts=2)
        report = runner.run(FlakyConnector(failures=99), FetchRequest(symbol="BTC/USDT"))
        assert not report.ok
        assert any("fetch failed after 2 attempts" in e for e in report.errors)
        assert store.read("curated", "flaky").empty

    def test_breaker_opens_and_skips_fetch_but_others_ingest(
        self, schemas: SchemaRegistry
    ) -> None:
        # Resilience acceptance (§7.4): a dying source degrades gracefully and
        # never takes down ingestion of the healthy ones.
        schemas.register(
            Schema(
                name="healthy",
                version=1,
                fields=SCHEMA.fields,
                primary_key=SCHEMA.primary_key,
            )
        )

        class HealthyConnector(FlakyConnector):
            metadata = ConnectorMetadata("healthy", "testing", "healthy", 3600)

        runner, store, _ = make_runner(schemas, max_attempts=1, breaker_threshold=2)
        dying = FlakyConnector(failures=99)
        req = FetchRequest(symbol="BTC/USDT")

        assert not runner.run(dying, req).ok  # failure 1
        assert not runner.run(dying, req).ok  # failure 2 -> circuit opens
        calls_before = dying.calls
        blocked = runner.run(dying, req)
        assert not blocked.ok
        assert any("circuit open" in e for e in blocked.errors)
        assert dying.calls == calls_before  # fetch was skipped entirely

        healthy = HealthyConnector(failures=0)
        assert runner.run(healthy, req).ok
        assert len(store.read("curated", "healthy")) == 6

    def test_ingest_twice_is_idempotent(self, schemas: SchemaRegistry) -> None:
        # Idempotency acceptance (§7.3): watermark + upsert — identical
        # curated row counts after a second run over the same window.
        runner, store, _ = make_runner(schemas)
        connector = FlakyConnector(failures=0)
        req = FetchRequest(symbol="BTC/USDT")
        assert runner.run(connector, req).ok
        first = store.read("curated", "flaky")
        assert runner.run(connector, req).ok
        second = store.read("curated", "flaky")
        assert len(first) == len(second) == 6
        # raw did not grow either: the watermark filtered already-seen rows
        assert len(store.read("raw", "flaky")) == 6

    def test_watermark_advances_and_resumes(self, schemas: SchemaRegistry) -> None:
        runner, store, _ = make_runner(schemas)
        connector = FlakyConnector(failures=0)
        runner.run(connector, FetchRequest(symbol="BTC/USDT"))
        wm = runner.watermarks.get("flaky", "BTC/USDT")
        assert wm == pd.Timestamp("2024-01-01 05:00", tz="UTC")

    def test_invalid_frame_never_reaches_curated(self, schemas: SchemaRegistry) -> None:
        class BadConnector(FlakyConnector):
            def synthetic(self, req: FetchRequest) -> FetchResult:
                rows = make_rows(req.symbol).drop(columns=["value"])  # schema breach
                return FetchResult(rows=rows, schema_version=1, source_mode="synthetic")

        runner, store, _ = make_runner(schemas)
        report = runner.run(BadConnector(), FetchRequest(symbol="BTC/USDT"))
        assert not report.ok
        assert store.read("curated", "flaky").empty


class TestWatermarkStore:
    def test_round_trip_and_isolation(self) -> None:
        store = DuckDBStore()
        marks = WatermarkStore(store)
        assert marks.get("market", "BTC/USDT") is None
        t1 = pd.Timestamp("2024-01-02", tz="UTC")
        marks.set("market", "BTC/USDT", t1)
        marks.set("market", "ETH/USDT", pd.Timestamp("2024-01-03", tz="UTC"))
        assert marks.get("market", "BTC/USDT") == t1
        marks.set("market", "BTC/USDT", pd.Timestamp("2024-01-05", tz="UTC"))
        assert marks.get("market", "BTC/USDT") == pd.Timestamp("2024-01-05", tz="UTC")
        assert len(marks.all()) == 2
