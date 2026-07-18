"""The Data Lake facade — what the rest of the platform talks to (§3.8).

``DataLake`` composes the registry (connector discovery, I7), the ingestion
runner (resilient + idempotent), the health monitor, the catalog and the
point-in-time FeatureStore (I2) behind five verbs: ``ingest``,
``repair_gaps``, ``snapshot``, ``catalog`` and ``health``.

``snapshot`` assembles a multi-channel :class:`MarketSnapshot` from the
curated tiers so **all** committee analysts can participate (0 abstentions);
``at`` builds historical point-in-time snapshots for research.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import quantos.data.connectors  # noqa: F401 — imports run connector discovery (I7)
from quantos.config import Settings
from quantos.data.catalog import DataCatalog
from quantos.data.connectors.base import FetchRequest
from quantos.data.connectors.registry import ConnectorRegistry
from quantos.data.connectors.registry import registry as default_registry
from quantos.data.featurestore import FeatureStore
from quantos.data.ingest.gaps import repair_gaps as _repair_gaps
from quantos.data.ingest.runner import IngestionRunner
from quantos.data.ingest.watermark import WatermarkStore
from quantos.data.models import OHLCV_COLUMNS, MarketSnapshot
from quantos.data.quality.monitor import HealthMonitor
from quantos.data.schema.registry import SchemaRegistry
from quantos.data.schema.registry import schema_registry as default_schema_registry
from quantos.data.schema.validation import DataValidator, ValidationReport
from quantos.data.store.base import Store
from quantos.data.store.duckdb_store import DuckDBStore

__all__ = ["DataLake"]

#: How each snapshot channel maps onto curated columns. Purely declarative —
#: adding a connector needs no change here unless it feeds a *new* channel.
_CHANNEL_FEATURES: dict[str, dict[str, str]] = {
    "derivatives": {
        "funding_rate": "derivatives.funding_rate",
        "open_interest_change": "derivatives.oi_change",
        "basis_bps": "derivatives.basis_bps",
        "long_short_ratio": "derivatives.long_short_ratio",
    },
    "onchain": {
        "net_exchange_flow": "onchain.net_exchange_flow",
        "whale_accumulation": "onchain.whale_accumulation",
        "stablecoin_supply_change": "onchain.stablecoin_supply_change",
    },
    "macro": {
        "dxy_trend": "macro.dxy_trend",
        "rates_trend": "macro.rates_trend",
        "risk_appetite": "macro.risk_appetite",
    },
    "sentiment": {
        "score": "sentiment.score",
        "volume": "sentiment.volume",
    },
}


class DataLake:
    """Facade over connectors, stores, ingestion, quality and features."""

    def __init__(
        self,
        store: Store | None = None,
        registry: ConnectorRegistry | None = None,
        schemas: SchemaRegistry | None = None,
        settings: Settings | None = None,
        monitor: HealthMonitor | None = None,
        runner: IngestionRunner | None = None,
    ) -> None:
        """
        Args:
            store: tiered backend; an in-memory :class:`DuckDBStore` when
                omitted (pass a rooted one to persist across processes).
            registry: connector registry (the module singleton by default).
            schemas: schema registry (the module singleton by default).
            settings: platform settings (seed, defaults).
            monitor: health monitor (a fresh one by default).
            runner: ingestion runner (built from the parts by default).
        """
        self.settings = settings or Settings()
        self.store: Store = store if store is not None else DuckDBStore()
        self.registry = registry or default_registry
        self.schemas = schemas or default_schema_registry
        self.monitor = monitor or HealthMonitor()
        self.features = FeatureStore(self.store)
        self.runner = runner or IngestionRunner(
            self.store,
            validator=DataValidator(),
            watermarks=WatermarkStore(self.store),
            monitor=self.monitor,
            schemas=self.schemas,
            seed=self.settings.seed,
        )

    # -- ingestion ------------------------------------------------------------

    def _connectors(self, categories: list[str] | None) -> list[Any]:
        if categories is None:
            return self.registry.all()
        return [c for cat in categories for c in self.registry.by_category(cat)]

    def ingest(
        self,
        symbol: str,
        timeframe: str = "1h",
        start: pd.Timestamp | str | None = None,
        end: pd.Timestamp | str | None = None,
        categories: list[str] | None = None,
        mode: str = "auto",
        limit: int = 1000,
    ) -> dict[str, ValidationReport]:
        """Run every registered connector (or a category subset) once.

        Each connector goes through the resilient runner: a failing source
        reports ``ok=False`` and never blocks the others. Re-running is
        idempotent (watermarks + curated upsert).

        Returns:
            ``{connector_name: ValidationReport}``.
        """
        reports: dict[str, ValidationReport] = {}
        for connector in self._connectors(categories):
            req = FetchRequest(
                symbol=symbol,
                start=start,
                end=end,
                timeframe=timeframe,
                limit=limit,
                mode=mode,
                seed=self.settings.seed,
            )
            reports[connector.metadata.name] = self.runner.run(connector, req)
        return reports

    def repair_gaps(
        self, symbol: str, timeframe: str = "1h", mode: str = "auto"
    ) -> dict[str, dict[str, Any]]:
        """Detect and backfill cadence gaps for every registered connector."""
        summaries: dict[str, dict[str, Any]] = {}
        for connector in self.registry.all():
            req = FetchRequest(
                symbol=symbol, timeframe=timeframe, mode=mode, seed=self.settings.seed
            )
            summaries[connector.metadata.name] = _repair_gaps(self.runner, connector, req)
        return summaries

    # -- point-in-time snapshot ------------------------------------------------

    def snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        at: pd.Timestamp | str | None = None,
    ) -> MarketSnapshot:
        """Assemble a point-in-time multi-channel :class:`MarketSnapshot`.

        Args:
            symbol: pair to snapshot.
            timeframe: bar timeframe of the OHLCV panel.
            limit: bars of history to carry.
            at: historical point in time; every channel is read as-of this
                moment (never later, I2). Defaults to the latest curated bar.

        Raises:
            ValueError: when no curated market data exists — run ``ingest``
                first (the lake never silently fabricates data).
        """
        market = self.store.read("curated", "market", symbol=symbol, end=at)
        if not market.empty and "timeframe" in market.columns:
            market = market[market["timeframe"] == timeframe]
        if market.empty:
            raise ValueError(
                f"no curated market data for {symbol!r} ({timeframe}); run ingest first"
            )
        market = market.sort_values("event_time", kind="stable").tail(limit)
        ohlcv = market.set_index("event_time")[list(OHLCV_COLUMNS)].astype(float)
        as_of = pd.Timestamp(market["event_time"].max()) if at is None else pd.Timestamp(at)

        channels: dict[str, Any] = {}
        for channel, mapping in _CHANNEL_FEATURES.items():
            values = self.features.as_of(symbol, as_of, list(mapping.values()))
            payload = {
                key: values[feature] for key, feature in mapping.items() if feature in values
            }
            if payload:
                channels[channel] = payload

        events = self._events(symbol, as_of)
        news = self._news(symbol, as_of)
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv=ohlcv,
            events=events,
            news=news,
            **channels,
        )

    def _events(self, symbol: str, as_of: pd.Timestamp) -> list[dict[str, Any]]:
        """Active macro event flags as snapshot events (drive the risk rules)."""
        values = self.features.as_of(symbol, as_of, ["macro.event_flag"])
        if values.get("macro.event_flag"):
            return [{"name": "macro_event", "impact": "high", "as_of": str(as_of)}]
        return []

    def _news(self, symbol: str, as_of: pd.Timestamp, last: int = 5) -> list[dict[str, Any]]:
        """The most recent tagged headlines at or before ``as_of`` (I2)."""
        frame = self.store.read("curated", "news", symbol=symbol, end=as_of)
        if frame.empty:
            return []
        frame = frame.sort_values("event_time", kind="stable").tail(last)
        return [
            {
                "time": str(row.event_time),
                "source": row.source,
                "headline": row.headline,
                "tag": row.tag,
                "sentiment": float(row.sentiment),
            }
            for row in frame.itertuples(index=False)
        ]

    # -- observability ---------------------------------------------------------

    def catalog(self) -> DataCatalog:
        """The queryable inventory of what the lake holds."""
        return DataCatalog(self.store, schemas=self.schemas, registry=self.registry)

    def health(self, now: pd.Timestamp | None = None) -> dict[str, Any]:
        """Per-connector freshness/success plus circuit-breaker states.

        Args:
            now: evaluation time (explicit in tests/research, I8); wall clock
                by default for live operation.
        """
        cadences = {
            c.metadata.name: c.metadata.cadence_seconds for c in self.registry.all()
        }
        report = self.monitor.report(cadences, now=now)
        for name in report:
            report[name]["circuit"] = self.runner.breaker(name).as_dict()
        return report
