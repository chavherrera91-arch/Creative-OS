"""The ingestion runner: fetch → validate → store → watermark → health.

One code path for every connector (I7):

1. **circuit-breaker gate** — an open circuit skips the fetch entirely so a
   dead source never stalls the others;
2. **fetch under RetryPolicy** — exponential backoff + jitter, injectable
   sleep (tests never wait);
3. **validate** against the latest registered schema — invalid frames never
   reach the curated tier;
4. **write raw + upsert curated** — raw keeps only rows beyond the
   watermark; curated upserts on the primary key, so re-running is
   idempotent;
5. **advance the watermark** — ingestion is resumable after a crash;
6. **record health** — success/failure, rows and freshness feed the monitor.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np
import pandas as pd

from quantos.data.connectors.base import Connector, FetchRequest, FetchResult
from quantos.data.ingest.retry import CircuitBreaker, RetryPolicy
from quantos.data.ingest.watermark import WatermarkStore
from quantos.data.schema.registry import SchemaRegistry
from quantos.data.schema.registry import schema_registry as default_schema_registry
from quantos.data.schema.validation import DataValidator, ValidationReport
from quantos.data.store.base import Store

__all__ = ["HealthRecorder", "IngestionRunner"]


class HealthRecorder(Protocol):
    """Where the runner reports outcomes (the HealthMonitor implements this)."""

    def record_success(
        self,
        connector: str,
        *,
        rows: int,
        last_event_time: pd.Timestamp | None,
        source_mode: str,
    ) -> None:
        """Record a successful run."""
        ...

    def record_failure(self, connector: str, *, error: str) -> None:
        """Record a failed run."""
        ...


class IngestionRunner:
    """Resilient, idempotent ingestion of any registered connector."""

    def __init__(
        self,
        store: Store,
        validator: DataValidator | None = None,
        watermarks: WatermarkStore | None = None,
        monitor: HealthRecorder | None = None,
        retry: RetryPolicy | None = None,
        *,
        schemas: SchemaRegistry | None = None,
        breaker_threshold: int = 5,
        breaker_reset_timeout: float = 300.0,
        sleep: Callable[[float], None] = time.sleep,
        seed: int = 42,
    ) -> None:
        """
        Args:
            store: tiered persistence backend.
            validator: schema validator (a default is built when omitted).
            watermarks: watermark store (built over ``store`` when omitted).
            monitor: optional health recorder.
            retry: fetch retry policy.
            schemas: schema registry (the module singleton when omitted).
            breaker_threshold: consecutive failures that open a circuit.
            breaker_reset_timeout: circuit cool-off seconds.
            sleep: backoff sleep function — injectable so tests never wait.
            seed: seed for backoff jitter (deterministic tests, I8).
        """
        self.store = store
        self.validator = validator or DataValidator()
        self.watermarks = watermarks or WatermarkStore(store)
        self.monitor = monitor
        self.retry = retry or RetryPolicy()
        self.schemas = schemas or default_schema_registry
        self._sleep = sleep
        self._rng = np.random.default_rng(seed)
        self._breaker_threshold = breaker_threshold
        self._breaker_reset_timeout = breaker_reset_timeout
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker(self, connector_name: str) -> CircuitBreaker:
        """The (lazily created) circuit breaker guarding one connector."""
        if connector_name not in self._breakers:
            self._breakers[connector_name] = CircuitBreaker(
                failure_threshold=self._breaker_threshold,
                reset_timeout=self._breaker_reset_timeout,
            )
        return self._breakers[connector_name]

    # -- pipeline -------------------------------------------------------------

    def _fail(self, connector: str, message: str) -> ValidationReport:
        if self.monitor is not None:
            self.monitor.record_failure(connector, error=message)
        return ValidationReport(ok=False, errors=[message])

    def run(self, connector: Connector, req: FetchRequest) -> ValidationReport:
        """Ingest one connector for one request. Idempotent.

        Returns:
            The validation report for the fetched frame; ``ok=False`` reports
            carry the failure reason (circuit open, fetch exhausted, invalid
            data) and nothing is written in those cases.
        """
        name = connector.metadata.name
        breaker = self.breaker(name)
        if not breaker.allow():
            return self._fail(name, f"circuit open for connector {name!r} (skipped fetch)")

        # Resume from the watermark: never re-fetch what is already curated.
        watermark = self.watermarks.get(name, req.symbol)
        effective = req
        if watermark is not None and (req.start is None or pd.Timestamp(req.start) <= watermark):
            effective = dataclasses.replace(req, start=watermark)

        try:
            result: FetchResult = self.retry.call(
                lambda: connector.fetch(effective), sleep=self._sleep, rng=self._rng
            )
        except Exception as exc:  # noqa: BLE001 — degrade, never take down the loop
            breaker.record(False)
            return self._fail(
                name, f"fetch failed after {self.retry.max_attempts} attempts: {exc}"
            )
        breaker.record(True)

        schema = self.schemas.latest(connector.metadata.schema_name)
        cleaned, report = self.validator.validate(result.rows, schema)
        if not report.ok:
            if self.monitor is not None:
                self.monitor.record_failure(name, error="; ".join(report.errors))
            return report

        time_col = schema.time_column
        new_rows = cleaned if watermark is None else cleaned[cleaned[time_col] > watermark]
        if not new_rows.empty:
            self.store.write("raw", name, new_rows, schema)
        self.store.upsert("curated", name, cleaned, keys=list(schema.primary_key))

        if not cleaned.empty:
            self.watermarks.set(name, req.symbol, pd.Timestamp(cleaned[time_col].max()))
        if self.monitor is not None:
            last_event = pd.Timestamp(cleaned[time_col].max()) if not cleaned.empty else None
            self.monitor.record_success(
                name,
                rows=len(cleaned),
                last_event_time=last_event,
                source_mode=result.source_mode,
            )
        return report
