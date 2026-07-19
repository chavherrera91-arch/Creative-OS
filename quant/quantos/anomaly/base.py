"""Anomaly detection contracts (module 4, ARCHITECTURE §2.4).

An :class:`AnomalyDetector` scores how unusual the market's behaviour is —
volume spikes, volatility bursts, price gaps, suspected wash-trading — so the
committee can treat "this market is behaving strangely" as explicit context
rather than noise. Detectors are pure functions of the data they are handed:
the score at bar *t* uses only bars ``<= t`` (invariant I2) and the same input
always yields the same output (I8).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd

__all__ = ["ANOMALY_KINDS", "AnomalyDetector", "anomaly_summary"]

#: The anomaly kinds every quantos detector reports on.
ANOMALY_KINDS: tuple[str, ...] = ("volume_spike", "volatility_burst", "gap", "wash_trading")


@runtime_checkable
class AnomalyDetector(Protocol):
    """Port for anomaly detectors (I7): fit / score / flags.

    ``score`` returns one value per bar, **higher = more anomalous**; ``flags``
    thresholds it into booleans. Implementations must be causal (I2) and
    deterministic (I8).
    """

    def fit(self, df: pd.DataFrame) -> AnomalyDetector:
        """Learn the detector's notion of "normal" from history; returns self."""
        ...

    def score(self, df: pd.DataFrame) -> pd.Series:
        """Per-bar anomaly score (higher = more anomalous), causal (I2)."""
        ...

    def flags(self, df: pd.DataFrame) -> pd.Series:
        """Per-bar boolean flags: True where the score clears the threshold."""
        ...


def anomaly_summary(detector: AnomalyDetector, ohlcv: pd.DataFrame) -> dict[str, Any]:
    """Point-in-time anomaly summary of the **last** bar (I2), for the committee.

    Args:
        detector: any :class:`AnomalyDetector`.
        ohlcv: bar frame; only its own bars are read — nothing is fetched.

    Returns:
        JSON-serialisable dict with the detector name, the last-bar composite
        ``score``, whether any anomaly is ``active``, the applied ``threshold``
        (NaN when the detector has none) and, when the detector exposes
        ``kind_scores``, a per-kind ``{"score", "flag"}`` breakdown (I4).
    """
    scores = detector.score(ohlcv)
    flags = detector.flags(ohlcv)
    threshold = float(getattr(detector, "threshold", float("nan")))
    kinds: dict[str, dict[str, Any]] = {}
    kind_scores = getattr(detector, "kind_scores", None)
    if callable(kind_scores):
        frame = kind_scores(ohlcv)
        kinds = {
            str(column): {
                "score": float(frame[column].iloc[-1]),
                "flag": bool(frame[column].iloc[-1] >= threshold),
            }
            for column in frame.columns
        }
    return {
        "detector": type(detector).__name__,
        "as_of": str(ohlcv.index[-1]),
        "active": bool(flags.iloc[-1]),
        "score": float(scores.iloc[-1]),
        "threshold": threshold,
        "kinds": kinds,
    }
