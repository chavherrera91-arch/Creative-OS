"""Connector framework: the plug-in contract for every data source.

A :class:`Connector` fetches one dataset (market, derivatives, on-chain, ...).
Adding a source means writing one ``Connector`` subclass and decorating it with
``@register`` (see :mod:`quantos.data.connectors.registry`) — **no core file is
edited** (Open/Closed, invariant I7).

Every connector must implement a deterministic :meth:`Connector.synthetic` mode
so the whole platform runs offline with no network and no keys (invariant I6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ConnectorMetadata:
    """Describes a connector for the registry, catalog and health monitor."""

    name: str
    category: str  # market | derivatives | onchain | macro | sentiment | news
    schema_name: str
    cadence_seconds: int  # expected update interval, used for freshness/lag
    offline_capable: bool = True


@dataclass(frozen=True)
class FetchRequest:
    """A request for one connector to fetch a window of data."""

    symbol: str
    start: Any = None
    end: Any = None
    timeframe: str = "1h"
    limit: int = 1000
    mode: str = "auto"  # auto | live | synthetic
    seed: int | None = None


@dataclass
class FetchResult:
    """The rows a connector produced, tagged with the schema version used."""

    rows: pd.DataFrame
    schema_version: int
    source_mode: str  # "live" | "synthetic"

    def __len__(self) -> int:
        return len(self.rows)


@dataclass
class HealthStatus:
    """A connector's operational health snapshot."""

    healthy: bool
    last_success: datetime | None = None
    last_error: str | None = None
    latency_ms: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


class Connector(ABC):
    """Base class for a data-source connector."""

    metadata: ConnectorMetadata

    @abstractmethod
    def fetch(self, req: FetchRequest) -> FetchResult:
        """Fetch a window. In ``auto`` mode, fall back to ``synthetic`` offline."""

    @abstractmethod
    def synthetic(self, req: FetchRequest) -> FetchResult:
        """Deterministic offline data for research/tests (invariant I6)."""

    def healthcheck(self) -> HealthStatus:
        """Cheap default probe: synthesise one row and report latency."""
        import time

        start = time.perf_counter()
        try:
            self.synthetic(FetchRequest(symbol="HEALTH", limit=1))
            latency = (time.perf_counter() - start) * 1000
            return HealthStatus(True, datetime.now(timezone.utc), None, latency)
        except Exception as exc:  # pragma: no cover - defensive
            return HealthStatus(False, None, str(exc), None)

    # -- helpers for subclasses ----------------------------------------------
    @staticmethod
    def _now() -> pd.Timestamp:
        return pd.Timestamp.now("UTC")

    def _stamp_ingested(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach the ingestion timestamp (distinct from event_time, I2)."""
        df = df.copy()
        df["ingested_at"] = self._now()
        return df
