"""Data models for market snapshots.

The Data Lake vision (OHLCV, derivatives, on-chain, macro, sentiment, news) is
represented here as a single :class:`MarketSnapshot` that carries the OHLCV
history plus optional side-channels. Analysts read from whatever is present and
abstain honestly when a channel is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass
class MarketSnapshot:
    """A point-in-time view of a market plus optional research context."""

    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame
    # Optional side-channels keyed by name. Absent -> analyst abstains.
    derivatives: dict[str, Any] = field(default_factory=dict)  # funding, OI, L/S
    onchain: dict[str, Any] = field(default_factory=dict)  # flows, whales
    macro: dict[str, Any] = field(default_factory=dict)  # DXY, rates, CPI
    sentiment: dict[str, Any] = field(default_factory=dict)  # social scores
    events: dict[str, Any] = field(default_factory=dict)  # FOMC, NFP flags
    news: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        missing = [c for c in OHLCV_COLUMNS if c not in self.ohlcv.columns]
        if missing:
            raise ValueError(f"OHLCV frame missing columns: {missing}")
        if self.ohlcv.empty:
            raise ValueError("OHLCV frame is empty")

    @property
    def close(self) -> pd.Series:
        return self.ohlcv["close"]

    @property
    def last_price(self) -> float:
        return float(self.ohlcv["close"].iloc[-1])

    @property
    def last_timestamp(self):
        return self.ohlcv.index[-1]

    def tail(self, n: int) -> "MarketSnapshot":
        """Return a snapshot truncated to the most recent ``n`` candles."""
        return MarketSnapshot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            ohlcv=self.ohlcv.tail(n).copy(),
            derivatives=self.derivatives,
            onchain=self.onchain,
            macro=self.macro,
            sentiment=self.sentiment,
            events=self.events,
            news=self.news,
        )
