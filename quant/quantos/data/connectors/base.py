"""The :class:`Connector` port — every data source is a plug-in (I7).

A connector fetches one dataset (market, funding, sentiment...) and always
ships a deterministic :meth:`Connector.synthetic` mode so the whole platform
runs offline with no keys (I6). Real backends are optional, lazy-imported by
the concrete connectors, and never hardcode credentials.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

__all__ = [
    "Connector",
    "ConnectorMetadata",
    "FetchRequest",
    "FetchResult",
    "HealthStatus",
]


@dataclass(frozen=True)
class ConnectorMetadata:
    """Static description of a connector.

    Attributes:
        name: unique connector name (also its curated table name).
        category: dataset category — ``market | derivatives | onchain |
            macro | sentiment | news``.
        schema_name: name of the registered schema its rows conform to.
        cadence_seconds: expected update interval, used for freshness/lag
            monitoring and gap detection.
        offline_capable: True when a deterministic synthetic mode exists
            (always True for shipped connectors, I6).
    """

    name: str
    category: str
    schema_name: str
    cadence_seconds: int
    offline_capable: bool = True

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "name": self.name,
            "category": self.category,
            "schema_name": self.schema_name,
            "cadence_seconds": self.cadence_seconds,
            "offline_capable": self.offline_capable,
        }


@dataclass(frozen=True)
class FetchRequest:
    """What to fetch.

    Attributes:
        symbol: trading pair, e.g. ``"BTC/USDT"``.
        start: inclusive lower bound on ``event_time`` (None = connector
            default window).
        end: inclusive upper bound on ``event_time``.
        timeframe: bar timeframe for bar-shaped datasets.
        limit: maximum rows to return.
        mode: ``"auto"`` (live when a real backend exists, else synthetic),
            ``"live"`` (require a real backend) or ``"synthetic"``.
        seed: seed for the synthetic generator (I8).
    """

    symbol: str
    start: pd.Timestamp | str | None = None
    end: pd.Timestamp | str | None = None
    timeframe: str = "1h"
    limit: int = 1000
    mode: str = "auto"
    seed: int = 42

    def __post_init__(self) -> None:
        if self.mode not in ("auto", "live", "synthetic"):
            raise ValueError(f"unknown fetch mode {self.mode!r}")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")


@dataclass
class FetchResult:
    """Rows returned by a connector.

    Attributes:
        rows: the fetched frame (must conform to the connector's schema).
        schema_version: version of the schema the rows conform to (I8).
        source_mode: ``"live"`` only when a real backend actually served the
            data; ``"synthetic"`` otherwise — the label never lies.
    """

    rows: pd.DataFrame
    schema_version: int
    source_mode: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (rows are not embedded)."""
        return {
            "rows": len(self.rows),
            "schema_version": self.schema_version,
            "source_mode": self.source_mode,
        }


@dataclass
class HealthStatus:
    """A connector's self-reported health.

    Attributes:
        healthy: True when the last probe/fetch succeeded.
        last_success: event time of the most recent successful fetch.
        last_error: message of the most recent failure, if any.
        latency_ms: duration of the last probe/fetch.
    """

    healthy: bool
    last_success: pd.Timestamp | None = None
    last_error: str | None = None
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "healthy": self.healthy,
            "last_success": str(self.last_success) if self.last_success is not None else None,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
        }


class Connector(ABC):
    """Base class for all data-source plug-ins.

    Subclasses set :attr:`metadata` and implement :meth:`fetch` and
    :meth:`synthetic`. ``synthetic`` must be a pure function of the request
    (deterministic, offline, I6/I8). ``fetch`` may use an optional real
    backend but must degrade to ``synthetic`` in ``"auto"`` mode.
    """

    metadata: ConnectorMetadata

    @abstractmethod
    def fetch(self, req: FetchRequest) -> FetchResult:
        """Fetch rows for a request, honouring ``req.mode``."""

    @abstractmethod
    def synthetic(self, req: FetchRequest) -> FetchResult:
        """Deterministic, offline rows for a request (I6, I8)."""

    def healthcheck(self) -> HealthStatus:
        """Cheap probe: run a tiny synthetic fetch and time it."""
        started = time.perf_counter()
        try:
            result = self.synthetic(
                FetchRequest(symbol="BTC/USDT", limit=2, mode="synthetic")
            )
        except Exception as exc:  # noqa: BLE001 — health must never raise
            return HealthStatus(healthy=False, last_error=str(exc))
        latency = (time.perf_counter() - started) * 1000.0
        last = None
        if not result.rows.empty and "event_time" in result.rows.columns:
            last = pd.Timestamp(result.rows["event_time"].max())
        return HealthStatus(healthy=True, last_success=last, latency_ms=latency)
