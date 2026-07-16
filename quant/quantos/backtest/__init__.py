"""Backtesting suite: vectorised backtest, walk-forward, Monte Carlo."""

from quantos.backtest.engine import BacktestResult, backtest, committee_signals
from quantos.backtest.metrics import performance_metrics
from quantos.backtest.monte_carlo import MonteCarloResult, monte_carlo
from quantos.backtest.walk_forward import WalkForwardResult, walk_forward

__all__ = [
    "BacktestResult",
    "MonteCarloResult",
    "WalkForwardResult",
    "backtest",
    "committee_signals",
    "monte_carlo",
    "performance_metrics",
    "walk_forward",
]
