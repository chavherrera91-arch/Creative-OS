"""Walk-forward analysis.

Splits the history into consecutive in-sample / out-of-sample folds and evaluates
the strategy only on the out-of-sample segments. A strategy that survives here is
far less likely to be curve-fit. An optional ``optimize`` hook lets a strategy
tune parameters on the in-sample window before being scored out-of-sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from quantos.backtest.engine import backtest
from quantos.backtest.metrics import performance_metrics

# signal_fn(ohlcv_window, params) -> target-position Series aligned to the window
SignalFn = Callable[[pd.DataFrame, dict], pd.Series]
# optimize_fn(train_ohlcv) -> params dict
OptimizeFn = Callable[[pd.DataFrame], dict]


@dataclass
class WalkForwardResult:
    folds: list[dict[str, Any]] = field(default_factory=list)
    combined_metrics: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"folds": self.folds, "combined": self.combined_metrics}


def walk_forward(
    ohlcv: pd.DataFrame,
    signal_fn: SignalFn,
    *,
    n_folds: int = 5,
    train_ratio: float = 0.6,
    optimize_fn: OptimizeFn | None = None,
    fee: float = 0.0004,
    periods_per_year: float = 8760.0,
) -> WalkForwardResult:
    n = len(ohlcv)
    if n < n_folds * 20:
        raise ValueError("history too short for the requested number of folds")

    fold_size = n // n_folds
    result = WalkForwardResult()
    oos_returns: list[pd.Series] = []

    for k in range(n_folds):
        start = k * fold_size
        end = n if k == n_folds - 1 else (k + 1) * fold_size
        segment = ohlcv.iloc[start:end]
        split = int(len(segment) * train_ratio)
        if split < 10 or len(segment) - split < 5:
            continue
        train, test = segment.iloc[:split], segment.iloc[split:]

        params = optimize_fn(train) if optimize_fn else {}
        positions = signal_fn(test, params)
        bt = backtest(test, positions, fee=fee, periods_per_year=periods_per_year)
        oos_returns.append(bt.returns)
        result.folds.append(
            {
                "fold": k,
                "train_size": len(train),
                "test_size": len(test),
                "params": params,
                "metrics": bt.metrics.as_dict(),
            }
        )

    if oos_returns:
        combined = pd.concat(oos_returns)
        result.combined_metrics = performance_metrics(
            combined, periods_per_year=periods_per_year
        ).as_dict()
    return result
