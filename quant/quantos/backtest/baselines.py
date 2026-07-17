"""Benchmark harness (ARCHITECTURE §9.1).

Every backtest reports its metrics **alongside buy-and-hold and a seeded random
baseline** — a strategy that cannot beat both is not evidence of an edge. This
guards against self-deception and complements invariant I9.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.backtest.metrics import HOURS_PER_YEAR, summarize

__all__ = ["random_positions", "vs_baselines"]


def random_positions(index: pd.Index, seed: int = 7) -> pd.Series:
    """Deterministic random positions in {-1, 0, +1} for a baseline strategy."""
    rng = np.random.default_rng(seed)
    return pd.Series(rng.integers(-1, 2, size=len(index)).astype(float), index=index)


def vs_baselines(
    returns: pd.Series,
    close: pd.Series,
    *,
    seed: int = 7,
    periods_per_year: float = HOURS_PER_YEAR,
) -> dict[str, object]:
    """Compare a strategy's returns against buy-and-hold and a random baseline.

    Args:
        returns: the strategy's net per-bar returns (already costed and lagged).
        close: the close-price series over the same index.
        seed: seed for the random baseline (reproducible, I8).
        periods_per_year: annualisation factor for the metrics.

    Returns:
        Dict with ``strategy`` / ``buy_and_hold`` / ``random`` metric dicts and
        ``beats_buy_and_hold`` / ``beats_random`` verdicts (Sharpe comparison).
    """
    close = close.reindex(returns.index).astype(float)
    market = close.pct_change().fillna(0.0)

    bh_returns = market  # long from the first bar, no leverage
    # The random baseline honours no-look-ahead too: positions are lagged (I2).
    rand_returns = random_positions(returns.index, seed=seed).shift(1).fillna(0.0) * market

    strategy = summarize(returns, periods_per_year)
    buy_and_hold = summarize(bh_returns, periods_per_year)
    random_ = summarize(rand_returns, periods_per_year)
    return {
        "strategy": strategy,
        "buy_and_hold": buy_and_hold,
        "random": random_,
        "beats_buy_and_hold": bool(strategy["sharpe"] > buy_and_hold["sharpe"]),
        "beats_random": bool(strategy["sharpe"] > random_["sharpe"]),
    }
