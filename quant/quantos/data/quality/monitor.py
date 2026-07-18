"""Health monitor: freshness, lag, success rate, rows, last error (§5).

Implements the runner's ``HealthRecorder`` protocol. A connector is marked
**stale** when ``now - last_event_time > stale_after × cadence`` — the signal
the dashboard (M8) and alerting build on. ``now`` is always an explicit
argument on the query side so every check is testable without a wall clock
(I6/I8); the wall clock is only the convenience default for live operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

__all__ = ["ConnectorHealth", "HealthMonitor"]


@dataclass
class ConnectorHealth:
    """Accumulated health state for one connector."""

    successes: int = 0
    failures: int = 0
    rows_total: int = 0
    last_rows: int = 0
    last_event_time: pd.Timestamp | None = None
    last_source_mode: str | None = None
    last_error: str | None = field(default=None)

    @property
    def runs(self) -> int:
        """Total recorded runs."""
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        """Fraction of successful runs (1.0 when nothing ran yet)."""
        return self.successes / self.runs if self.runs else 1.0


class HealthMonitor:
    """Collects per-connector ingestion outcomes and derives health status."""

    def __init__(self, stale_after: float = 3.0) -> None:
        """
        Args:
            stale_after: staleness threshold in cadence multiples — a
                connector whose last event is older than ``stale_after ×
                cadence`` is flagged stale.
        """
        self.stale_after = stale_after
        self._health: dict[str, ConnectorHealth] = {}

    def _entry(self, connector: str) -> ConnectorHealth:
        return self._health.setdefault(connector, ConnectorHealth())

    # -- HealthRecorder protocol ----------------------------------------------

    def record_success(
        self,
        connector: str,
        *,
        rows: int,
        last_event_time: pd.Timestamp | None,
        source_mode: str,
    ) -> None:
        """Record one successful ingestion run."""
        entry = self._entry(connector)
        entry.successes += 1
        entry.rows_total += rows
        entry.last_rows = rows
        entry.last_source_mode = source_mode
        entry.last_error = None
        if last_event_time is not None:
            entry.last_event_time = pd.Timestamp(last_event_time)

    def record_failure(self, connector: str, *, error: str) -> None:
        """Record one failed ingestion run."""
        entry = self._entry(connector)
        entry.failures += 1
        entry.last_error = error

    # -- queries ---------------------------------------------------------------

    def status(
        self,
        connector: str,
        cadence_seconds: int,
        now: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        """Health status of one connector.

        Args:
            connector: connector name.
            cadence_seconds: its expected update interval.
            now: evaluation time — pass explicitly in tests/research (I8);
                defaults to the wall clock for live operation only.
        """
        now = now if now is not None else pd.Timestamp.now(tz="UTC")
        entry = self._entry(connector)
        lag: float | None = None
        stale = entry.last_event_time is None
        if entry.last_event_time is not None:
            lag = float((now - entry.last_event_time).total_seconds())
            stale = lag > self.stale_after * cadence_seconds
        return {
            "connector": connector,
            "healthy": entry.last_error is None and not stale,
            "stale": stale,
            "lag_seconds": lag,
            "cadence_seconds": cadence_seconds,
            "runs": entry.runs,
            "success_rate": entry.success_rate,
            "rows_total": entry.rows_total,
            "last_rows": entry.last_rows,
            "last_event_time": (
                str(entry.last_event_time) if entry.last_event_time is not None else None
            ),
            "last_source_mode": entry.last_source_mode,
            "last_error": entry.last_error,
        }

    def report(
        self, cadences: dict[str, int], now: pd.Timestamp | None = None
    ) -> dict[str, dict[str, Any]]:
        """Status for every known connector, keyed by name.

        Args:
            cadences: ``{connector: cadence_seconds}`` (from the registry).
            now: evaluation time (explicit in tests, I8).
        """
        names = sorted(set(self._health) | set(cadences))
        return {
            name: self.status(name, cadences.get(name, 3600), now=now) for name in names
        }
