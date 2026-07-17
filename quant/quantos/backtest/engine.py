"""Vectorised backtest engine (module 7, M1 scope).

The engine's one sacred rule is **no look-ahead** (invariant I2): the position
used for the P&L of bar *t* is the position decided at bar *t-1*
(``positions.shift(1)``). Costs are charged on turnover. Every result reports
its metrics **alongside buy-and-hold and a random baseline**
(:func:`quantos.backtest.baselines.vs_baselines`) so an edge is never claimed
without beating both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.backtest.baselines import vs_baselines
from quantos.backtest.metrics import HOURS_PER_YEAR, equity_curve, summarize
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.data.models import MarketSnapshot

__all__ = ["BacktestResult", "backtest", "committee_signals"]


@dataclass
class BacktestResult:
    """Everything a backtest run produced.

    Attributes:
        positions: the *decided* (un-lagged) target positions in [-1, 1].
        returns: net per-bar strategy returns (lagged positions, costs charged).
        equity: compounded equity curve (starts at 1.0).
        metrics: standard metrics dict for the strategy.
        baselines: metrics vs buy-and-hold and the seeded random baseline.
        n_trades: number of position changes (turnover events).
        fee_bps: fee assumption used.
        slippage_bps: slippage assumption used.
    """

    positions: pd.Series
    returns: pd.Series
    equity: pd.Series
    metrics: dict[str, float]
    baselines: dict[str, Any] = field(default_factory=dict)
    n_trades: int = 0
    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (series omitted, metrics kept)."""
        return {
            "metrics": dict(self.metrics),
            "baselines": dict(self.baselines),
            "n_trades": self.n_trades,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "final_equity": float(self.equity.iloc[-1]) if len(self.equity) else 1.0,
        }


def backtest(
    ohlcv: pd.DataFrame,
    positions: pd.Series,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    periods_per_year: float = HOURS_PER_YEAR,
    baseline_seed: int = 7,
) -> BacktestResult:
    """Run a vectorised backtest of target positions over OHLCV.

    Args:
        ohlcv: bar frame with a ``close`` column.
        positions: target position per bar in [-1, 1], decided *at* that bar.
            The engine lags it by one bar before computing P&L (I2).
        fee_bps: fee per unit of turnover, basis points.
        slippage_bps: slippage per unit of turnover, basis points.
        periods_per_year: annualisation factor for metrics.
        baseline_seed: seed for the random baseline (I8).

    Returns:
        A :class:`BacktestResult` with metrics and mandatory baselines.
    """
    close = ohlcv["close"].astype(float)
    pos = positions.reindex(close.index).fillna(0.0).clip(-1.0, 1.0).astype(float)

    lagged = pos.shift(1).fillna(0.0)  # I2: decided at t-1, held during t
    market = close.pct_change().fillna(0.0)
    gross = lagged * market

    turnover = lagged.diff().abs().fillna(lagged.abs())
    costs = turnover * (fee_bps + slippage_bps) / 10_000.0
    net = gross - costs

    return BacktestResult(
        positions=pos,
        returns=net,
        equity=equity_curve(net),
        metrics=summarize(net, periods_per_year),
        baselines=vs_baselines(net, close, seed=baseline_seed, periods_per_year=periods_per_year),
        n_trades=int((turnover > 0).sum()),
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )


def committee_signals(
    ohlcv: pd.DataFrame,
    committee: InvestmentCommittee | None = None,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    warmup: int = 60,
    step: int = 1,
    context: dict[str, Any] | None = None,
) -> pd.Series:
    """Generate target positions by deliberating the committee bar by bar.

    At each decision bar the committee sees **only bars up to and including
    that bar** (I2); the resulting stance is held until the next decision bar.
    Deterministic for a fixed committee + data (I8).

    Args:
        ohlcv: full bar history.
        committee: committee to consult; the default bench when omitted.
        symbol: symbol label for the snapshots.
        timeframe: timeframe label for the snapshots.
        warmup: bars to stay flat while indicators warm up.
        step: deliberate every ``step`` bars (positions carry forward between).
        context: optional deliberation context forwarded to the committee.

    Returns:
        Target position series in {-1.0, 0.0, +1.0} indexed like ``ohlcv``.
    """
    committee = committee or default_committee()
    positions = pd.Series(0.0, index=ohlcv.index)
    current = 0.0
    for i in range(len(ohlcv)):
        if i >= warmup and (i - warmup) % step == 0:
            snapshot = MarketSnapshot(symbol=symbol, timeframe=timeframe, ohlcv=ohlcv.iloc[: i + 1])
            decision = committee.deliberate(snapshot, context)
            current = float(decision.direction.sign) if decision.approved else 0.0
        positions.iloc[i] = current
    return positions
