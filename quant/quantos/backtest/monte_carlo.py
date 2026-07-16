"""Monte Carlo robustness analysis.

Given a strategy's per-bar returns, resample them many times to build a
distribution of outcomes. This answers "was the backtest lucky?" — the spread of
final returns and the distribution of worst-case drawdowns matter more than a
single equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quantos.backtest.metrics import max_drawdown


@dataclass
class MonteCarloResult:
    n_sims: int
    final_return: dict[str, float]
    max_drawdown: dict[str, float]
    prob_loss: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_sims": self.n_sims,
            "final_return": {k: round(v, 4) for k, v in self.final_return.items()},
            "max_drawdown": {k: round(v, 4) for k, v in self.max_drawdown.items()},
            "prob_loss": round(self.prob_loss, 4),
        }


def monte_carlo(
    returns: pd.Series,
    *,
    n_sims: int = 1000,
    method: str = "bootstrap",
    seed: int | None = 42,
) -> MonteCarloResult:
    """Resample ``returns`` to estimate outcome dispersion.

    ``method`` = ``"bootstrap"`` samples returns with replacement (breaks serial
    structure) or ``"permutation"`` shuffles the observed returns (preserves the
    multiset, varies path/drawdown).
    """
    r = returns.fillna(0.0).to_numpy()
    r = r[r == r]  # drop any NaNs defensively
    if len(r) == 0:
        raise ValueError("empty returns series")

    rng = np.random.default_rng(seed)
    finals = np.empty(n_sims)
    drawdowns = np.empty(n_sims)

    for i in range(n_sims):
        if method == "permutation":
            sample = rng.permutation(r)
        else:
            sample = rng.choice(r, size=len(r), replace=True)
        equity = np.cumprod(1.0 + sample)
        finals[i] = equity[-1] - 1.0
        drawdowns[i] = max_drawdown(pd.Series(equity))

    def pctiles(a: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(np.mean(a)),
            "p05": float(np.percentile(a, 5)),
            "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95)),
        }

    return MonteCarloResult(
        n_sims=n_sims,
        final_return=pctiles(finals),
        max_drawdown=pctiles(drawdowns),
        prob_loss=float(np.mean(finals < 0)),
    )
