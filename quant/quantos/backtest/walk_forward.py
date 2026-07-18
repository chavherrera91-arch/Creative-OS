"""Walk-forward analysis: strictly out-of-sample evaluation folds.

The sample is split into an initial training window and ``n_folds``
consecutive test windows. For each fold the signal function only ever sees
data up to the end of that fold (and must itself be causal, I2); the fold's
metrics are computed **only on its out-of-sample window**, with position/cost
continuity preserved across the fold boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.backtest.baselines import vs_baselines
from quantos.backtest.engine import backtest
from quantos.backtest.metrics import HOURS_PER_YEAR, summarize
from quantos.backtest.validation import deflated_sharpe_from_returns

__all__ = ["WalkForwardFold", "WalkForwardResult", "walk_forward"]

SignalFn = Callable[[pd.DataFrame], pd.Series]


@dataclass
class WalkForwardFold:
    """One out-of-sample fold."""

    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_test_bars: int
    metrics: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "fold": self.fold,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "n_test_bars": self.n_test_bars,
            "metrics": dict(self.metrics),
        }


@dataclass
class WalkForwardResult:
    """All folds plus the aggregate out-of-sample view.

    ``validation`` carries the anti-overfitting report (per-period Sharpe,
    skew, kurtosis and the Deflated Sharpe Ratio for the stated number of
    trials) over the concatenated OOS returns — no walk-forward edge is ever
    reported without it (invariant I9).
    """

    folds: list[WalkForwardFold] = field(default_factory=list)
    oos_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    oos_metrics: dict[str, float] = field(default_factory=dict)
    baselines: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "folds": [f.as_dict() for f in self.folds],
            "oos_metrics": dict(self.oos_metrics),
            "baselines": dict(self.baselines),
            "validation": dict(self.validation),
        }


def walk_forward(
    ohlcv: pd.DataFrame,
    signal_fn: SignalFn,
    n_folds: int = 4,
    min_train: int = 100,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    periods_per_year: float = HOURS_PER_YEAR,
    baseline_seed: int = 7,
    n_trials: int = 1,
) -> WalkForwardResult:
    """Run walk-forward out-of-sample evaluation.

    Args:
        ohlcv: full bar history.
        signal_fn: causal function mapping an OHLCV prefix to target positions
            (it is only ever handed data up to the end of the fold under test).
        n_folds: number of consecutive OOS test windows.
        min_train: bars reserved for the initial training window.
        fee_bps: fee assumption.
        slippage_bps: slippage assumption.
        periods_per_year: annualisation factor.
        baseline_seed: seed for the aggregate random baseline.
        n_trials: how many strategy variants were tried before this one was
            selected — deflates the reported Sharpe accordingly (I9). Be
            honest here: understating it overstates the edge.

    Returns:
        A :class:`WalkForwardResult`; ``oos_metrics`` covers the concatenated
        out-of-sample returns only and ``validation`` carries its Deflated
        Sharpe report (I9).
    """
    n = len(ohlcv)
    if n <= min_train + n_folds:
        raise ValueError(f"not enough bars ({n}) for min_train={min_train}, n_folds={n_folds}")
    test_size = (n - min_train) // n_folds

    folds: list[WalkForwardFold] = []
    oos_parts: list[pd.Series] = []
    for k in range(n_folds):
        train_end = min_train + k * test_size
        test_end = n if k == n_folds - 1 else train_end + test_size
        visible = ohlcv.iloc[:test_end]  # never beyond the fold under test (I2)
        positions = signal_fn(visible)
        result = backtest(
            visible,
            positions,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            periods_per_year=periods_per_year,
            baseline_seed=baseline_seed,
        )
        oos = result.returns.iloc[train_end:test_end]
        oos_parts.append(oos)
        folds.append(
            WalkForwardFold(
                fold=k,
                train_start=str(ohlcv.index[0]),
                train_end=str(ohlcv.index[train_end - 1]),
                test_start=str(ohlcv.index[train_end]),
                test_end=str(ohlcv.index[test_end - 1]),
                n_test_bars=test_end - train_end,
                metrics=summarize(oos, periods_per_year),
            )
        )

    oos_returns = pd.concat(oos_parts)
    close = ohlcv["close"].reindex(oos_returns.index)
    return WalkForwardResult(
        folds=folds,
        oos_returns=oos_returns,
        oos_metrics=summarize(oos_returns, periods_per_year),
        baselines=vs_baselines(
            oos_returns, close, seed=baseline_seed, periods_per_year=periods_per_year
        ),
        validation=deflated_sharpe_from_returns(oos_returns, n_trials=n_trials),
    )
