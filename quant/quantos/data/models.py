"""Core market data model.

``MarketSnapshot`` is the single object every analyst reads (ARCHITECTURE
§2.3). It always carries OHLCV; every other channel (derivatives, on-chain,
macro, sentiment, events, news) is optional — analysts whose channel is absent
must abstain honestly (invariant I3), never fabricate conviction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

__all__ = ["OHLCV_COLUMNS", "MarketSnapshot"]

OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


@dataclass
class MarketSnapshot:
    """Point-in-time view of a market across data channels.

    Attributes:
        symbol: trading pair, e.g. ``"BTC/USDT"``.
        timeframe: bar timeframe, e.g. ``"1h"``.
        ohlcv: bar frame indexed by time with columns ``open/high/low/close/volume``.
        derivatives: optional dict (funding rate, open interest, basis, ...).
        onchain: optional dict (exchange flows, whale accumulation, ...).
        macro: optional dict (DXY trend, rates, event calendar distance, ...).
        sentiment: optional dict (aggregate score in [-1, 1], per-platform, ...).
        events: optional list of scheduled/market events (dicts with at least
            ``name`` and ``impact``).
        news: optional list of tagged headlines (dicts).
    """

    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame
    derivatives: dict[str, Any] | None = None
    onchain: dict[str, Any] | None = None
    macro: dict[str, Any] | None = None
    sentiment: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    news: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the OHLCV contract on construction."""
        if not isinstance(self.ohlcv, pd.DataFrame):
            raise TypeError("MarketSnapshot.ohlcv must be a pandas DataFrame")
        missing = [c for c in OHLCV_COLUMNS if c not in self.ohlcv.columns]
        if missing:
            raise ValueError(f"MarketSnapshot.ohlcv missing columns: {missing}")
        if len(self.ohlcv) == 0:
            raise ValueError("MarketSnapshot.ohlcv is empty")
        if not self.ohlcv.index.is_monotonic_increasing:
            raise ValueError("MarketSnapshot.ohlcv index must be monotonic increasing (I2)")

    @property
    def last_price(self) -> float:
        """Close of the most recent bar."""
        return float(self.ohlcv["close"].iloc[-1])

    @property
    def as_of(self) -> str:
        """Timestamp of the most recent bar (the decision's point in time, I2)."""
        return str(self.ohlcv.index[-1])

    @property
    def bars(self) -> int:
        """Number of bars carried."""
        return len(self.ohlcv)

    def has(self, channel: str) -> bool:
        """True if an optional channel is present and non-empty."""
        value = getattr(self, channel, None)
        return bool(value)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (the full frame is not embedded)."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": self.bars,
            "as_of": self.as_of,
            "last_price": self.last_price,
            "channels": {
                name: self.has(name)
                for name in ("derivatives", "onchain", "macro", "sentiment", "events", "news")
            },
        }
