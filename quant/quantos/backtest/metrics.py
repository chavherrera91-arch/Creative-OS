"""Performance metrics for return series.

All functions take a per-bar simple-return :class:`pandas.Series` and are pure,
deterministic and NaN-tolerant (NaNs are treated as flat bars). ``summarize``
bundles them into the standard metrics dict every backtest reports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "HOURS_PER_YEAR",
    "annualized_volatility",
    "equity_curve",
    "max_drawdown",
    "profit_factor",
    "sharpe_ratio",
    "sortino_ratio",
    "summarize",
    "total_return",
    "win_rate",
]

#: Periods per year for 24/7 crypto hourly bars — the platform default timeframe.
HOURS_PER_YEAR: float = 24.0 * 365.0


def _clean(returns: pd.Series) -> pd.Series:
    """Treat missing bars as flat (0 return)."""
    return returns.fillna(0.0).astype(float)


def equity_curve(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Compound per-bar returns into an equity curve starting at ``initial``."""
    return initial * (1.0 + _clean(returns)).cumprod()


def total_return(returns: pd.Series) -> float:
    """Total compounded return over the whole series (0.10 == +10%)."""
    if len(returns) == 0:
        return 0.0
    return float((1.0 + _clean(returns)).prod() - 1.0)


def annualized_volatility(returns: pd.Series, periods_per_year: float = HOURS_PER_YEAR) -> float:
    """Annualised standard deviation of per-bar returns."""
    r = _clean(returns)
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, periods_per_year: float = HOURS_PER_YEAR) -> float:
    """Annualised Sharpe ratio (risk-free rate 0). 0.0 when volatility is 0."""
    r = _clean(returns)
    if len(r) < 2:
        return 0.0
    std = float(r.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(r.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: float = HOURS_PER_YEAR) -> float:
    """Annualised Sortino ratio (downside deviation only). 0.0 when no downside."""
    r = _clean(returns)
    if len(r) < 2:
        return 0.0
    downside = r[r < 0.0]
    if len(downside) == 0:
        return 0.0
    dd = float(np.sqrt((downside**2).mean()))
    if dd == 0.0:
        return 0.0
    return float(r.mean() / dd * np.sqrt(periods_per_year))


def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough drawdown of the equity curve, as a negative number."""
    if len(returns) == 0:
        return 0.0
    curve = equity_curve(returns)
    peak = curve.cummax()
    return float((curve / peak - 1.0).min())


def win_rate(returns: pd.Series) -> float:
    """Fraction of non-flat bars with a positive return (0.0 if none traded)."""
    r = _clean(returns)
    active = r[r != 0.0]
    if len(active) == 0:
        return 0.0
    return float((active > 0.0).mean())


def profit_factor(returns: pd.Series) -> float:
    """Gross profits / gross losses. ``inf`` if no losses but some profits."""
    r = _clean(returns)
    gains = float(r[r > 0.0].sum())
    losses = float(-r[r < 0.0].sum())
    if losses == 0.0:
        return float("inf") if gains > 0.0 else 0.0
    return gains / losses


def summarize(returns: pd.Series, periods_per_year: float = HOURS_PER_YEAR) -> dict[str, float]:
    """The standard metrics dict reported by every backtest."""
    return {
        "total_return": total_return(returns),
        "sharpe": sharpe_ratio(returns, periods_per_year),
        "sortino": sortino_ratio(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "volatility": annualized_volatility(returns, periods_per_year),
        "win_rate": win_rate(returns),
        "profit_factor": profit_factor(returns),
        "n_bars": float(len(returns)),
    }
