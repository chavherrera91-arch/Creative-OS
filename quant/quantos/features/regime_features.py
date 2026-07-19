"""Regime feature set (M4): no-look-ahead features that characterise state.

Everything the Market Regime Engine reasons over lives here: trend strength
(ADX, EMA slope), realised and ATR volatility, range-vs-trend character
(Hurst exponent, Kaufman efficiency ratio), the volume regime, and proximity
to macro events from the snapshot's ``events`` channel.

All series functions are **strictly causal** (invariant I2): the value at bar
*t* depends only on bars ``<= t`` — rolling/expanding windows and recursive
EWMs, never centered windows or future shifts. Everything is a pure function
of its inputs (I8). Warm-up bars are NaN rather than fabricated.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind

__all__ = [
    "adx",
    "ema_slope",
    "efficiency_ratio",
    "event_proximity",
    "hurst_exponent",
    "regime_feature_frame",
    "snapshot_regime_features",
]

#: Impact weights for event proximity, by calendar impact level.
_EVENT_WEIGHTS: dict[str, float] = {"high": 1.0, "medium": 0.5, "low": 0.2}


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder), in [0, 100] — trend *strength*.

    Directional movement and true range are smoothed with Wilder's recursive
    EWM (causal); the ADX is the same smoothing applied to the DX series.
    High readings mean a strong trend in either direction.
    """
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0.0), 0.0)
    minus_dm = down.where((down > up) & (down > 0.0), 0.0)

    alpha = 1.0 / period
    tr_smooth = ind.true_range(high, low, close).ewm(
        alpha=alpha, adjust=False, min_periods=period
    ).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / tr_smooth
    minus_di = (
        100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / tr_smooth
    )

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def ema_slope(close: pd.Series, period: int = 50, lookback: int = 10) -> pd.Series:
    """Per-bar fractional slope of the ``period``-EMA over ``lookback`` bars.

    ``(ema_t / ema_{t-lookback} - 1) / lookback`` — a signed trend direction
    measure: ≈ the average per-bar drift of the smoothed price.
    """
    smoothed = ind.ema(close, period)
    return (smoothed / smoothed.shift(lookback) - 1.0) / lookback


def efficiency_ratio(close: pd.Series, period: int = 20) -> pd.Series:
    """Kaufman efficiency ratio in [0, 1]: net move over path length.

    1 means every bar moved the same way (pure trend); near 0 means the path
    wandered without getting anywhere (range).
    """
    net = (close - close.shift(period)).abs()
    path = close.diff().abs().rolling(window=period, min_periods=period).sum()
    return net / path.replace(0.0, np.nan)


def hurst_exponent(close: pd.Series, max_lag: int = 20, window: int = 128) -> float:
    """Hurst exponent of the trailing ``window`` bars (aggregated-variance method).

    Fits ``log rms(x_{t+τ} - x_t) ~ H · log τ`` over ``τ = 2..max_lag`` on the
    log-price tail (root-mean-square differences, so persistent drift counts
    as persistence). H > 0.5 = persistent/trending, H < 0.5 = mean-reverting,
    H ≈ 0.5 = random walk. A scalar of the *prefix* it is handed — causal by
    construction (I2). Returns 0.5 when the sample is too short or flat.
    """
    tail = np.log(close.astype(float).to_numpy()[-window:])
    if len(tail) < max_lag * 2:
        return 0.5
    lags = np.arange(2, max_lag + 1)
    spreads = np.array([np.sqrt(np.mean((tail[lag:] - tail[:-lag]) ** 2)) for lag in lags])
    if np.any(spreads <= 0.0):
        return 0.5
    slope = np.polyfit(np.log(lags), np.log(spreads), 1)[0]
    return float(np.clip(slope, 0.0, 1.0))


def event_proximity(
    events: list[dict[str, Any]] | None,
    as_of: Any = None,
    horizon_hours: float = 48.0,
) -> float:
    """Proximity score in [0, 1] to the nearest impactful calendar event.

    Each event contributes ``weight(impact) · (1 - |hours from as_of| /
    horizon)``, floored at 0; the score is the maximum contribution. An event
    without a parseable ``time`` field is treated as imminent (distance 0) —
    if it is on the calendar with no timestamp, caution wins. 1.0 therefore
    means "a high-impact event is happening now".

    Args:
        events: the snapshot's ``events`` channel (dicts with at least
            ``name`` and ``impact``; optionally ``time``).
        as_of: the snapshot's point in time, for events that carry a ``time``.
        horizon_hours: distance at which an event stops mattering.
    """
    if not events:
        return 0.0
    anchor: pd.Timestamp | None = None
    if as_of is not None:
        try:
            anchor = pd.Timestamp(as_of)
        except (TypeError, ValueError):
            anchor = None
    best = 0.0
    for event in events:
        weight = _EVENT_WEIGHTS.get(str(event.get("impact", "")).lower(), 0.0)
        if weight <= 0.0:
            continue
        hours = 0.0
        when = event.get("time")
        if when is not None and anchor is not None:
            try:
                hours = abs((pd.Timestamp(when) - anchor).total_seconds()) / 3600.0
            except (TypeError, ValueError):
                hours = 0.0
        best = max(best, weight * max(0.0, 1.0 - hours / horizon_hours))
    return float(best)


def regime_feature_frame(
    ohlcv: pd.DataFrame,
    vol_window: int = 20,
    trend_period: int = 14,
    er_period: int = 20,
) -> pd.DataFrame:
    """Per-bar regime features, every column strictly causal (I2).

    Columns:
        ``adx`` — trend strength in [0, 100].
        ``ema_slope`` — signed per-bar fractional EMA(50) slope.
        ``trend_intensity`` — ``ema_slope`` in units of realised vol (signed,
            dimensionless drift-to-noise ratio).
        ``efficiency_ratio`` — range-vs-trend character in [0, 1].
        ``realised_vol`` — rolling std of 1-bar returns.
        ``vol_ratio`` — realised vol vs its own *expanding* median (causal).
        ``atr_pct`` — ATR(14) as a fraction of price.
        ``volume_ratio`` — recent mean volume vs its expanding median.
        ``drawdown`` — close vs its running peak (≤ 0).

    Returns:
        DataFrame indexed like ``ohlcv``; warm-up bars are NaN.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)

    realised_vol = ind.rolling_volatility(close, vol_window)
    vol_median = realised_vol.expanding(min_periods=vol_window).median()
    slope = ema_slope(close)
    volume_recent = volume.rolling(window=vol_window, min_periods=vol_window).mean()
    volume_median = volume.expanding(min_periods=vol_window).median()

    return pd.DataFrame(
        {
            "adx": adx(high, low, close, trend_period),
            "ema_slope": slope,
            "trend_intensity": slope / realised_vol.replace(0.0, np.nan),
            "efficiency_ratio": efficiency_ratio(close, er_period),
            "realised_vol": realised_vol,
            "vol_ratio": realised_vol / vol_median.replace(0.0, np.nan),
            "atr_pct": ind.atr(high, low, close, trend_period) / close,
            "volume_ratio": volume_recent / volume_median.replace(0.0, np.nan),
            "drawdown": close / close.cummax() - 1.0,
        },
        index=ohlcv.index,
    )


def snapshot_regime_features(snapshot: MarketSnapshot) -> dict[str, float]:
    """Point-in-time regime features for a snapshot (the classifier's input).

    The last row of :func:`regime_feature_frame` — every statistic uses only
    the snapshot's own bars, all of which are ``<= as_of`` (I2) — plus the
    trailing-window Hurst exponent and the macro-event proximity from the
    ``events`` channel. NaNs (short history) are neutralised to regime-neutral
    values so the classifier always has a defined input.
    """
    frame = regime_feature_frame(snapshot.ohlcv)
    last = frame.iloc[-1]
    neutral = {
        "adx": 0.0,
        "ema_slope": 0.0,
        "trend_intensity": 0.0,
        "efficiency_ratio": 0.0,
        "realised_vol": 0.0,
        "vol_ratio": 1.0,
        "atr_pct": 0.0,
        "volume_ratio": 1.0,
        "drawdown": 0.0,
    }
    features = {
        name: float(last[name]) if np.isfinite(last[name]) else default
        for name, default in neutral.items()
    }
    features["hurst"] = hurst_exponent(snapshot.ohlcv["close"])
    features["event_proximity"] = event_proximity(snapshot.events, as_of=snapshot.ohlcv.index[-1])
    return features
