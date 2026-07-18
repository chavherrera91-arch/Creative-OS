"""Market (OHLCV) connector — wraps the M1 collector behind the plug-in port.

Reuses :mod:`quantos.data.collector` (read-only ccxt + deterministic
synthetic generator) rather than forking it. ``source_mode`` is labelled
``"live"`` only when a real exchange actually served the candles; every
offline path is honestly labelled ``"synthetic"``.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.collector import DataCollector, synthetic_ohlcv
from quantos.data.connectors._synthetic import CANONICAL_PERIODS, slice_window
from quantos.data.connectors.base import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
)
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["MARKET_SCHEMA", "MarketConnector"]

MARKET_SCHEMA = Schema(
    name="market",
    version=1,
    fields=(
        FieldSpec("symbol", "string", description="trading pair"),
        FieldSpec("timeframe", "string", description="bar timeframe, e.g. 1h"),
        FieldSpec("event_time", "datetime", description="bar open time (point-in-time key, I2)"),
        FieldSpec("ingested_at", "datetime", description="when the row entered the lake"),
        FieldSpec("open", "float64", min=0.0, unit="quote"),
        FieldSpec("high", "float64", min=0.0, unit="quote"),
        FieldSpec("low", "float64", min=0.0, unit="quote"),
        FieldSpec("close", "float64", min=0.0, unit="quote"),
        FieldSpec("volume", "float64", min=0.0, unit="base"),
    ),
    primary_key=("symbol", "timeframe", "event_time"),
)
schema_registry.register(MARKET_SCHEMA)


def _shape_rows(ohlcv: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """Turn an index-by-time OHLCV frame into schema-shaped rows."""
    rows = ohlcv.reset_index(names="event_time")
    rows.insert(0, "symbol", symbol)
    rows.insert(1, "timeframe", timeframe)
    return rows


@register
class MarketConnector(Connector):
    """OHLCV candles: ccxt when installed and reachable, synthetic otherwise."""

    metadata = ConnectorMetadata(
        name="market",
        category="market",
        schema_name="market",
        cadence_seconds=3600,
    )

    def fetch(self, req: FetchRequest) -> FetchResult:
        """Fetch candles honouring ``req.mode``.

        ``"live"`` requires a real exchange (raises offline); ``"auto"``
        tries the exchange and falls back to :meth:`synthetic`; the result is
        labelled ``"live"`` only when ccxt actually served it.
        """
        if req.mode == "synthetic":
            return self.synthetic(req)
        collector = DataCollector(force_synthetic=False)
        frame = collector.fetch_ohlcv(req.symbol, req.timeframe, bars=req.limit, seed=req.seed)
        if collector.last_source == "ccxt":
            rows = _shape_rows(frame, req.symbol, req.timeframe)
            rows["ingested_at"] = pd.Timestamp.now(tz="UTC")
            return FetchResult(
                rows=slice_window(rows, req),
                schema_version=MARKET_SCHEMA.version,
                source_mode="live",
            )
        if req.mode == "live":
            raise RuntimeError(
                "market connector has no live backend available (ccxt/network); "
                "use mode='auto' or 'synthetic' for the offline path (I6)"
            )
        return self.synthetic(req)

    def synthetic(self, req: FetchRequest) -> FetchResult:
        """Deterministic candles from the canonical seeded series (I6, I8).

        The full canonical series is generated and then sliced, so any
        sub-window re-fetch reproduces exactly the same values — ingestion
        stays idempotent and gap repair is loss-free.
        """
        ohlcv = synthetic_ohlcv(
            req.symbol, req.timeframe, bars=CANONICAL_PERIODS, seed=req.seed
        )
        rows = _shape_rows(ohlcv, req.symbol, req.timeframe)
        rows["ingested_at"] = rows["event_time"]  # deterministic: no wall clock (I8)
        return FetchResult(
            rows=slice_window(rows, req),
            schema_version=MARKET_SCHEMA.version,
            source_mode="synthetic",
        )
