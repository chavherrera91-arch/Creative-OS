"""Anomaly detectors (module 4, M4 scope).

Two implementations of the :class:`~quantos.anomaly.base.AnomalyDetector`
port:

* :class:`ZScoreDetector` — the dependency-free baseline (numpy + pandas
  only, I6). Per-kind causal z-scores over volume spikes, volatility bursts,
  price gaps and suspected wash-trading; the composite score is the worst
  kind at each bar.
* :class:`IsolationForestDetector` — an optional multivariate detector over
  the same feature set, behind the ``[ml]`` extra (scikit-learn is imported
  lazily and never required by tests).

Every feature is **causal**: the baseline statistics behind the z-score at
bar *t* are computed from bars ``< t`` (rolling windows shifted by one), so a
spike cannot camouflage itself inside its own baseline and no value ever
reads the future (invariant I2).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantos.anomaly.base import ANOMALY_KINDS

__all__ = ["IsolationForestDetector", "ZScoreDetector", "anomaly_features"]


def _causal_zscore(series: pd.Series, window: int) -> pd.Series:
    """Z-score of each value against the *prior* ``window`` bars (I2).

    The rolling mean/std are shifted by one bar so the value being scored is
    never part of its own baseline — an outlier at *t* cannot inflate the
    statistics used to judge it.
    """
    mean = series.rolling(window=window, min_periods=window // 2).mean().shift(1)
    std = series.rolling(window=window, min_periods=window // 2).std(ddof=1).shift(1)
    return (series - mean) / std.replace(0.0, np.nan)


def anomaly_features(ohlcv: pd.DataFrame, window: int = 48) -> pd.DataFrame:
    """Per-kind causal anomaly scores, in comparable "sigma" units.

    Columns (one per :data:`~quantos.anomaly.base.ANOMALY_KINDS` entry):

    * ``volume_spike`` — z-score of log-volume vs its prior window.
    * ``volatility_burst`` — |1-bar return| in units of the prior window's
      return volatility.
    * ``gap`` — |open vs previous close| in the same volatility units.
    * ``wash_trading`` — geometric mean of "volume unusually high" and
      "bar range unusually narrow": heavy prints that move nothing are the
      classic fake-liquidity signature.

    All statistics at bar *t* use only bars ``< t`` (I2); warm-up bars are NaN.

    Args:
        ohlcv: bar frame with ``open/high/low/close/volume`` columns.
        window: baseline window for the rolling statistics.

    Returns:
        DataFrame indexed like ``ohlcv`` with one score column per kind.
    """
    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float)

    volume_z = _causal_zscore(np.log1p(volume), window)

    ret = close.pct_change()
    ret_std = ret.rolling(window=window, min_periods=window // 2).std(ddof=1).shift(1)
    ret_std = ret_std.replace(0.0, np.nan)
    burst = ret.abs() / ret_std

    gap_frac = (ohlcv["open"].astype(float) / close.shift(1) - 1.0).abs()
    gap = gap_frac / ret_std

    range_frac = (ohlcv["high"].astype(float) - ohlcv["low"].astype(float)) / close
    range_z = _causal_zscore(range_frac, window)
    heavy = volume_z.clip(lower=0.0)
    narrow = (-range_z).clip(lower=0.0)
    wash = np.sqrt(heavy * narrow)

    return pd.DataFrame(
        {
            "volume_spike": volume_z,
            "volatility_burst": burst,
            "gap": gap,
            "wash_trading": wash,
        },
        index=ohlcv.index,
    )[list(ANOMALY_KINDS)]


class ZScoreDetector:
    """Dependency-free baseline anomaly detector (numpy + pandas only, I6).

    Scores each bar as the **worst** per-kind causal z-score from
    :func:`anomaly_features` and flags bars whose composite score clears
    :attr:`threshold`. Stateless by design: "normal" is the trailing window
    of the data being scored, so :meth:`fit` is a no-op kept for the
    :class:`~quantos.anomaly.base.AnomalyDetector` port.
    """

    def __init__(self, threshold: float = 4.0, window: int = 48) -> None:
        """
        Args:
            threshold: sigma level a kind must reach to flag a bar.
            window: baseline window for the rolling statistics.
        """
        self.threshold = threshold
        self.window = window

    def fit(self, df: pd.DataFrame) -> ZScoreDetector:
        """No-op (the baseline is the trailing window); returns self."""
        return self

    def kind_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Per-kind causal scores with warm-up NaNs neutralised to 0."""
        return anomaly_features(df, window=self.window).fillna(0.0)

    def score(self, df: pd.DataFrame) -> pd.Series:
        """Composite per-bar score: the worst kind at each bar (higher = worse)."""
        return self.kind_scores(df).max(axis=1)

    def flags(self, df: pd.DataFrame) -> pd.Series:
        """True where the composite score clears :attr:`threshold`."""
        return self.score(df) >= self.threshold


class IsolationForestDetector:
    """Isolation-forest detector over the same causal feature set (``[ml]``).

    scikit-learn is imported **lazily** on first fit — importing this module
    never requires it (I6) and the offline test suite exercises only the
    :class:`ZScoreDetector` baseline.

    Note:
        The forest learns "normal" from whatever frame :meth:`fit` receives.
        For point-in-time research the fit window must precede the scored
        window (I2) — fitting and scoring the same frame is only appropriate
        for retrospective data-quality sweeps.
    """

    def __init__(
        self,
        threshold: float = 0.55,
        window: int = 48,
        n_estimators: int = 100,
        contamination: float | str = "auto",
        seed: int = 42,
    ) -> None:
        """
        Args:
            threshold: flag level on the normalised score in [0, 1].
            window: baseline window for the causal input features.
            n_estimators: number of trees.
            contamination: sklearn contamination parameter.
            seed: random state — the forest is deterministic for a fixed
                seed and input (I8).
        """
        self.threshold = threshold
        self.window = window
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.seed = seed
        self._model: Any = None

    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        return anomaly_features(df, window=self.window).fillna(0.0)

    def fit(self, df: pd.DataFrame) -> IsolationForestDetector:
        """Fit the forest on ``df``'s causal features (lazy sklearn import)."""
        try:
            from sklearn.ensemble import IsolationForest  # noqa: PLC0415 — [ml] extra
        except ImportError as exc:  # pragma: no cover - exercised without sklearn
            raise ImportError(
                "IsolationForestDetector requires scikit-learn — install the "
                "'ml' extra (pip install quantos[ml]) or use the "
                "dependency-free ZScoreDetector baseline"
            ) from exc
        self._model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.seed,
        )
        self._model.fit(self._features(df).to_numpy())
        return self

    def score(self, df: pd.DataFrame) -> pd.Series:
        """Per-bar anomaly score in [0, 1] (higher = more anomalous)."""
        if self._model is None:
            self.fit(df)
        raw = -self._model.score_samples(self._features(df).to_numpy())
        return pd.Series(raw, index=df.index)

    def flags(self, df: pd.DataFrame) -> pd.Series:
        """True where the score clears :attr:`threshold`."""
        return self.score(df) >= self.threshold
