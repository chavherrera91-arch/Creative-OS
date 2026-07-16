"""Vectorised backtest engine + committee-driven signal generation.

``backtest`` is strategy-agnostic: give it a positions series and it returns an
equity curve and metrics with transaction costs and no look-ahead (positions are
lagged one bar before being applied to returns).

``committee_signals`` walks an OHLCV history and asks the
:class:`InvestmentCommittee` for a decision at each rebalance point — this is the
research-first path from "the committee decided" to "here's how it would have
performed", without ever touching real capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from quantos.backtest.metrics import PerformanceMetrics, equity_curve, performance_metrics
from quantos.committee.committee import InvestmentCommittee
from quantos.data.models import MarketSnapshot


@dataclass
class BacktestResult:
    returns: pd.Series
    equity: pd.Series
    positions: pd.Series
    metrics: PerformanceMetrics

    def summary(self) -> dict[str, Any]:
        return {"metrics": self.metrics.as_dict(), "final_equity": float(self.equity.iloc[-1])}


def backtest(
    ohlcv: pd.DataFrame,
    positions: pd.Series,
    *,
    fee: float = 0.0004,
    periods_per_year: float = 8760.0,
) -> BacktestResult:
    """Backtest a target-position series against an OHLCV frame.

    ``positions`` holds the target exposure (-1..1) decided *using data up to and
    including* each bar; it is lagged one bar before being applied, so the fill
    happens on the next bar's return — no look-ahead.
    """
    positions = positions.reindex(ohlcv.index).fillna(0.0)
    asset_returns = ohlcv["close"].pct_change().fillna(0.0)

    # Cost is charged on the bar where exposure changes.
    trades = positions.diff().abs()
    trades.iloc[0] = abs(positions.iloc[0])
    cost = trades * fee

    strat_returns = positions.shift(1).fillna(0.0) * asset_returns - cost
    equity = equity_curve(strat_returns)
    metrics = performance_metrics(strat_returns, periods_per_year=periods_per_year)
    return BacktestResult(
        returns=strat_returns, equity=equity, positions=positions, metrics=metrics
    )


def committee_signals(
    committee: InvestmentCommittee,
    ohlcv: pd.DataFrame,
    *,
    symbol: str = "ASSET",
    timeframe: str = "1h",
    warmup: int = 100,
    step: int = 1,
    context_provider: Callable[[int, pd.DataFrame], dict] | None = None,
) -> pd.Series:
    """Generate a target-position series by running the committee bar-by-bar.

    ``step`` rebalances every N bars (>1 is far cheaper on long histories). The
    position between rebalances is held. ``context_provider(i, window)`` may
    supply per-bar side-channels (macro/sentiment/on-chain/events).
    """
    positions = np.zeros(len(ohlcv))
    current = 0.0
    for i in range(warmup, len(ohlcv)):
        if (i - warmup) % step == 0:
            window = ohlcv.iloc[: i + 1]
            context = context_provider(i, window) if context_provider else None
            snapshot = MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                ohlcv=window,
                **_split_context(context),
            )
            decision = committee.deliberate(snapshot, context)
            current = float(decision.direction.sign)
        positions[i] = current
    return pd.Series(positions, index=ohlcv.index, name="position")


def _split_context(context: dict | None) -> dict:
    """Map a flat context dict onto MarketSnapshot side-channel kwargs."""
    if not context:
        return {}
    keys = ("derivatives", "onchain", "macro", "sentiment", "events", "news")
    return {k: context[k] for k in keys if k in context}
