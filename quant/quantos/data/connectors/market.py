"""Market connector: OHLCV candles.

Wraps the existing read-only collection logic (ccxt when available, deterministic
synthetic otherwise) behind the :class:`Connector` interface, emitting rows that
conform to the registered ``market`` schema. Registers itself on import via
``@register`` (invariant I7) and its schema into the default schema registry.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.collector import DataCollector, _ccxt_available, synthetic_ohlcv
from quantos.data.connectors.base import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
)
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

MARKET_SCHEMA = Schema(
    name="market",
    version=1,
    fields=(
        FieldSpec("symbol", "string", description="Instrument symbol"),
        FieldSpec("event_time", "datetime64[ns, UTC]", description="Candle open time"),
        FieldSpec("ingested_at", "datetime64[ns, UTC]", description="Ingestion time"),
        FieldSpec("open", "float64", min=0.0),
        FieldSpec("high", "float64", min=0.0),
        FieldSpec("low", "float64", min=0.0),
        FieldSpec("close", "float64", min=0.0),
        FieldSpec("volume", "float64", min=0.0),
    ),
    primary_key=("symbol", "event_time"),
)

# Register the schema once (import is idempotent within a process).
if "market" not in schema_registry.names():
    schema_registry.register(MARKET_SCHEMA)


@register
class MarketConnector(Connector):
    metadata = ConnectorMetadata(
        name="market",
        category="market",
        schema_name="market",
        cadence_seconds=3600,  # 1h candles by default
        offline_capable=True,
    )

    def __init__(self, source: str = "auto") -> None:
        self._collector = DataCollector(source=source)

    # -- Connector API --------------------------------------------------------
    def fetch(self, req: FetchRequest) -> FetchResult:
        # In auto mode we only attempt a live fetch when a real backend exists;
        # otherwise the result is genuinely synthetic and must be labelled so.
        if req.mode == "synthetic" or (req.mode == "auto" and not _ccxt_available()):
            return self.synthetic(req)
        try:
            ohlcv = self._collector.fetch_ohlcv(req.symbol, req.timeframe, req.limit)
            return FetchResult(self._shape(ohlcv, req.symbol), MARKET_SCHEMA.version, "live")
        except Exception:
            if req.mode == "live":
                raise  # explicit live request must surface the error
            return self.synthetic(req)

    def synthetic(self, req: FetchRequest) -> FetchResult:
        ohlcv = synthetic_ohlcv(req.symbol, req.timeframe, req.limit, seed=req.seed)
        return FetchResult(self._shape(ohlcv, req.symbol), MARKET_SCHEMA.version, "synthetic")

    # -- helpers --------------------------------------------------------------
    def _shape(self, ohlcv: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Reshape an indexed OHLCV frame into the tabular market schema."""
        df = ohlcv.reset_index().rename(columns={"timestamp": "event_time"})
        if "event_time" not in df.columns:  # index had a different name
            df = df.rename(columns={df.columns[0]: "event_time"})
        df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
        df.insert(0, "symbol", symbol)
        df = self._stamp_ingested(df)
        cols = ["symbol", "event_time", "ingested_at", "open", "high", "low", "close", "volume"]
        return df[cols]
