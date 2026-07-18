"""WP-2.3 — connector framework: contracts, self-registration, zero core edits."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest

from quantos.data.connectors import (
    Connector,
    ConnectorMetadata,
    ConnectorRegistry,
    FetchRequest,
    FetchResult,
    register,
    registry,
)


def dummy_rows(req: FetchRequest, n: int = 3) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": [req.symbol] * n,
            "event_time": times,
            "ingested_at": times,
            "value": [1.0, 2.0, 3.0],
        }
    )


class DummyConnector(Connector):
    """Minimal connector used to prove the plug-in contract."""

    metadata = ConnectorMetadata(
        name="dummy",
        category="testing",
        schema_name="dummy",
        cadence_seconds=3600,
    )

    def fetch(self, req: FetchRequest) -> FetchResult:
        return self.synthetic(req)

    def synthetic(self, req: FetchRequest) -> FetchResult:
        return FetchResult(rows=dummy_rows(req), schema_version=1, source_mode="synthetic")


@pytest.fixture()
def clean_dummy() -> Iterator[None]:
    yield
    registry.unregister("dummy")


class TestContracts:
    def test_fetch_request_validates_mode_and_limit(self) -> None:
        with pytest.raises(ValueError):
            FetchRequest(symbol="BTC/USDT", mode="download")
        with pytest.raises(ValueError):
            FetchRequest(symbol="BTC/USDT", limit=0)

    def test_default_healthcheck_probes_synthetic(self) -> None:
        status = DummyConnector().healthcheck()
        assert status.healthy
        assert status.latency_ms is not None and status.latency_ms >= 0.0
        assert status.as_dict()["healthy"] is True

    def test_fetch_result_serialises(self) -> None:
        result = DummyConnector().synthetic(FetchRequest(symbol="BTC/USDT"))
        payload = result.as_dict()
        assert payload == {"rows": 3, "schema_version": 1, "source_mode": "synthetic"}


class TestRegistry:
    def test_decorator_self_registers_with_zero_core_edits(self, clean_dummy: None) -> None:
        # Registering requires ONLY this decorator — no edit to base.py,
        # registry.py or lake.py (invariant I7).
        assert "dummy" not in registry.names()
        register(DummyConnector)
        assert registry.get("dummy").metadata.category == "testing"
        assert "dummy" in [c.metadata.name for c in registry.all()]
        assert [c.metadata.name for c in registry.by_category("testing")] == ["dummy"]

    def test_get_unknown_name_raises_with_hint(self) -> None:
        fresh = ConnectorRegistry()
        with pytest.raises(KeyError):
            fresh.get("nope")

    def test_ordering_is_deterministic(self) -> None:
        fresh = ConnectorRegistry()

        class A(DummyConnector):
            metadata = ConnectorMetadata("b_conn", "testing", "dummy", 60)

        class B(DummyConnector):
            metadata = ConnectorMetadata("a_conn", "testing", "dummy", 60)

        fresh.register(A())
        fresh.register(B())
        assert [c.metadata.name for c in fresh.all()] == ["a_conn", "b_conn"]
