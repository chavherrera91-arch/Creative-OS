"""Performance metrics computed from a returns series.

Metrics are annualisation-aware via ``periods_per_year`` (e.g. 8760 for hourly
bars, 365 for daily crypto). Everything is derived from the per-bar strategy
returns so the same code serves backtest, walk-forward and Monte Carlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    volatility: float
    win_rate: float
    profit_factor: float
    n_periods: int
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_return": round(self.total_return, 4),
            "cagr": round(self.cagr, 4),
            "sharpe": round(self.sharpe, 3),
            "sortino": round(self.sortino, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "volatility": round(self.volatility, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 3),
            "n_periods": self.n_periods,
            **self.extra,
        }


def equity_curve(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    return initial * (1.0 + returns.fillna(0.0)).cumprod()


def max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min()) if len(drawdown) else 0.0


def performance_metrics(
    returns: pd.Series, periods_per_year: float = 8760.0
) -> PerformanceMetrics:
    r = returns.fillna(0.0)
    n = int(len(r))
    if n == 0:
        return PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)

    equity = equity_curve(r)
    total_return = float(equity.iloc[-1] - 1.0)

    mean, std = float(r.mean()), float(r.std())
    volatility = std * np.sqrt(periods_per_year)
    sharpe = (mean / std * np.sqrt(periods_per_year)) if std > 0 else 0.0

    downside = r[r < 0]
    dstd = float(downside.std()) if len(downside) > 1 else 0.0
    sortino = (mean / dstd * np.sqrt(periods_per_year)) if dstd > 0 else 0.0

    years = n / periods_per_year
    cagr = float(equity.iloc[-1] ** (1 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else 0.0

    nonzero = r[r != 0]
    wins = nonzero[nonzero > 0]
    losses = nonzero[nonzero < 0]
    win_rate = float(len(wins) / len(nonzero)) if len(nonzero) else 0.0
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (np.inf if gross_win > 0 else 0.0)

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown(equity),
        volatility=volatility,
        win_rate=win_rate,
        profit_factor=profit_factor,
        n_periods=n,
    )
