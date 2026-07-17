"""Vectorised technical indicators — strictly causal (invariant I2).

Every function is a pure transformation where the value at bar *t* depends only
on data at bars ``<= t`` (rolling windows and recursive EWMs, never centered
windows or shifts into the future). Warm-up bars are NaN rather than fabricated.

The no-look-ahead property is asserted over generated inputs in
``tests/test_invariants_property.py`` and on fixtures in
``tests/test_indicators.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "atr",
    "bollinger",
    "ema",
    "macd",
    "returns",
    "rolling_volatility",
    "rsi",
    "sma",
    "true_range",
    "zscore",
]


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average over ``period`` bars (NaN during warm-up)."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, span ``period``, recursive form.

    ``adjust=False`` gives the standard recursive EMA:
    ``ema_t = alpha * x_t + (1 - alpha) * ema_{t-1}`` with
    ``alpha = 2 / (period + 1)`` — causal by construction.
    """
    return series.ewm(span=period, adjust=False).mean()


def returns(series: pd.Series, period: int = 1) -> pd.Series:
    """Simple percentage returns over ``period`` bars (NaN for the first bars)."""
    return series.pct_change(periods=period)


def rolling_volatility(series: pd.Series, period: int = 20) -> pd.Series:
    """Rolling standard deviation of 1-bar returns over ``period`` bars."""
    return returns(series).rolling(window=period, min_periods=period).std(ddof=1)


def zscore(series: pd.Series, period: int = 20) -> pd.Series:
    """Rolling z-score: distance from the ``period``-bar mean in std units."""
    mean = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std(ddof=1)
    return (series - mean) / std.replace(0.0, np.nan)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder's smoothing, in [0, 100].

    All-gain windows read 100, all-loss windows read 0.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    out = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    out = out.where(avg_loss != 0.0, 100.0)  # no losses -> RSI 100
    out = out.where((avg_gain != 0.0) | (avg_loss != 0.0), 50.0)  # perfectly flat -> neutral
    return out.where(avg_gain.notna() & avg_loss.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: max(high-low, |high-prev_close|, |low-prev_close|)."""
    prev_close = close.shift(1)
    ranges = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return ranges.max(axis=1, skipna=False).fillna(high - low)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range with Wilder's smoothing (NaN during warm-up)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal line and histogram.

    Returns:
        DataFrame with columns ``macd`` (fast EMA − slow EMA), ``signal``
        (EMA of the MACD line) and ``histogram`` (macd − signal).
    """
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": macd_line - signal_line}
    )


def bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands.

    Returns:
        DataFrame with columns ``middle`` (SMA), ``upper``, ``lower`` and
        ``percent_b`` (position of price within the bands: 0 = lower, 1 = upper).
    """
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=1)
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {"middle": middle, "upper": upper, "lower": lower, "percent_b": (series - lower) / width}
    )
