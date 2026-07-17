"""Monte Carlo resampling of a backtest's returns.

Bootstrap-resamples the per-bar return series (seeded, reproducible — I8) to
estimate the *distribution* of outcomes rather than the single realised path:
percentile bands of total return, probability of loss, and drawdown tails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["MonteCarloResult", "monte_carlo"]


@dataclass
class MonteCarloResult:
    """Distributional view of a strategy's outcomes.

    Attributes:
        n_sims: number of bootstrap simulations.
        seed: RNG seed used (I8).
        total_return_percentiles: p05/p25/p50/p75/p95 of total return.
        max_drawdown_percentiles: p05/p50/p95 of max drawdown (negative values).
        prob_loss: fraction of simulations ending below breakeven.
        mean_total_return: mean simulated total return.
    """

    n_sims: int
    seed: int
    total_return_percentiles: dict[str, float] = field(default_factory=dict)
    max_drawdown_percentiles: dict[str, float] = field(default_factory=dict)
    prob_loss: float = 0.0
    mean_total_return: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "n_sims": self.n_sims,
            "seed": self.seed,
            "total_return_percentiles": dict(self.total_return_percentiles),
            "max_drawdown_percentiles": dict(self.max_drawdown_percentiles),
            "prob_loss": self.prob_loss,
            "mean_total_return": self.mean_total_return,
        }


def monte_carlo(returns: pd.Series, n_sims: int = 500, seed: int = 42) -> MonteCarloResult:
    """Bootstrap-resample a return series into an outcome distribution.

    Args:
        returns: net per-bar strategy returns (e.g. ``BacktestResult.returns``).
        n_sims: number of resampled paths.
        seed: RNG seed — the whole result is a pure function of
            ``(returns, n_sims, seed)`` (I8).

    Returns:
        A :class:`MonteCarloResult` with ordered percentile bands.
    """
    values = returns.fillna(0.0).to_numpy(dtype=float)
    n = len(values)
    if n == 0:
        raise ValueError("returns series is empty")
    rng = np.random.default_rng(seed)

    idx = rng.integers(0, n, size=(n_sims, n))
    paths = values[idx]
    equity = np.cumprod(1.0 + paths, axis=1)
    totals = equity[:, -1] - 1.0
    peaks = np.maximum.accumulate(equity, axis=1)
    drawdowns = (equity / peaks - 1.0).min(axis=1)

    tr_p = np.percentile(totals, [5, 25, 50, 75, 95])
    dd_p = np.percentile(drawdowns, [5, 50, 95])
    return MonteCarloResult(
        n_sims=n_sims,
        seed=seed,
        total_return_percentiles={
            "p05": float(tr_p[0]),
            "p25": float(tr_p[1]),
            "p50": float(tr_p[2]),
            "p75": float(tr_p[3]),
            "p95": float(tr_p[4]),
        },
        max_drawdown_percentiles={
            "p05": float(dd_p[0]),
            "p50": float(dd_p[1]),
            "p95": float(dd_p[2]),
        },
        prob_loss=float((totals < 0.0).mean()),
        mean_total_return=float(totals.mean()),
    )
