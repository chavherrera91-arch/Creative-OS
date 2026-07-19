"""Regime classifiers (module 14, M4 scope).

:class:`RuleRegimeClassifier` is the deterministic, dependency-free baseline
(numpy + pandas only, I6): an explicit rule hierarchy over the point-in-time
regime features of :mod:`quantos.features.regime_features`, mirroring the
Chair's own decision style — auditable rules, not a black box. Every call
returns a :class:`~quantos.regime.base.RegimeState` with probabilities,
features and signed evidence (I4), and the same snapshot always yields the
same state (I8).

:class:`GmmRegimeClassifier` and :class:`HmmRegimeClassifier` are optional
statistical backends behind the ``[ml]`` extra (scikit-learn / hmmlearn,
imported lazily, never required by tests). They fit a mixture/HMM over the
causal feature frame and map each learned component to a regime label by
scoring the component's mean feature vector with the same rule engine — so
even the ML path stays explainable.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantos.committee.base import Evidence
from quantos.data.models import MarketSnapshot
from quantos.features.regime_features import regime_feature_frame, snapshot_regime_features
from quantos.regime.base import REGIME_LABELS, UNTRADEABLE_LABELS, RegimeState

__all__ = ["GmmRegimeClassifier", "HmmRegimeClassifier", "RuleRegimeClassifier"]


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


class RuleRegimeClassifier:
    """Deterministic rule-hierarchy regime classifier (the offline baseline).

    The label is decided by an explicit cascade — macro event ▶ crisis ▶
    high vol ▶ trend ▶ low vol ▶ range — and the probabilities are the
    normalised per-label scores behind it. When the cascade and the raw
    scores disagree (rare, by design near boundaries), the hierarchy is
    authoritative and the winning label's score is lifted to the top before
    normalising, so ``label`` is always the argmax of ``probabilities``.
    """

    name = "RuleRegimeClassifier"

    def __init__(
        self,
        adx_trend: float = 25.0,
        trend_bar: float = 0.7,
        vol_high: float = 2.0,
        vol_low: float = 0.6,
        crisis_vol: float = 3.0,
        crisis_drawdown: float = -0.20,
        event_gate: float = 0.5,
        untradeable: frozenset[str] = UNTRADEABLE_LABELS,
    ) -> None:
        """
        Args:
            adx_trend: ADX level treated as full trend strength.
            trend_bar: composite trend strength required to call a trend.
            vol_high: vol ratio (vs its own median) that means HIGH_VOL.
            vol_low: vol ratio at or below which the market is LOW_VOL.
            crisis_vol: vol ratio required (with the drawdown) for CRISIS.
            crisis_drawdown: running-peak drawdown required for CRISIS.
            event_gate: event proximity at which MACRO_EVENT takes over.
            untradeable: labels the Chair's regime gate stands down on.
        """
        self.adx_trend = adx_trend
        self.trend_bar = trend_bar
        self.vol_high = vol_high
        self.vol_low = vol_low
        self.crisis_vol = crisis_vol
        self.crisis_drawdown = crisis_drawdown
        self.event_gate = event_gate
        self.untradeable = frozenset(untradeable)

    # -- scoring ---------------------------------------------------------

    def trend_strength(self, features: dict[str, float]) -> float:
        """Composite trend strength in [0, ~1.2] from ADX, ER and drift/noise."""
        adx = features.get("adx", 0.0)
        er = features.get("efficiency_ratio", 0.0)
        ti = features.get("trend_intensity", 0.0)
        return (
            0.5 * _clip01(adx / self.adx_trend)
            + 0.3 * _clip01(er)
            + 0.4 * _clip01(abs(ti))
        )

    def scores(self, features: dict[str, float]) -> dict[str, float]:
        """Raw, non-negative per-label scores (the probability numerators)."""
        vol_ratio = features.get("vol_ratio", 1.0)
        drawdown = features.get("drawdown", 0.0)
        proximity = features.get("event_proximity", 0.0)
        ti = features.get("trend_intensity", features.get("ema_slope", 0.0))
        er = features.get("efficiency_ratio", 0.0)
        adx = features.get("adx", 0.0)

        trend = self.trend_strength(features)
        event = 2.4 * proximity if proximity >= self.event_gate else 0.4 * proximity
        crisis = (
            2.0
            * _clip01(vol_ratio / self.crisis_vol)
            * _clip01(drawdown / self.crisis_drawdown)
        )
        return {
            "TREND_UP": trend if ti > 0 else 0.05 * trend,
            "TREND_DOWN": trend if ti < 0 else 0.05 * trend,
            "RANGE": 0.8 * (1.0 - _clip01(er)) * (1.0 - _clip01(adx / (2.0 * self.adx_trend))),
            "HIGH_VOL": 1.3 * _clip01((vol_ratio - 1.0) / (self.vol_high - 1.0)),
            "LOW_VOL": 0.9 * _clip01((1.0 - vol_ratio) / (1.0 - self.vol_low)),
            "MACRO_EVENT": event,
            "CRISIS": crisis,
        }

    def cascade(self, features: dict[str, float]) -> str:
        """The authoritative label hierarchy (ARCHITECTURE §3, step 1 feed)."""
        vol_ratio = features.get("vol_ratio", 1.0)
        drawdown = features.get("drawdown", 0.0)
        ti = features.get("trend_intensity", features.get("ema_slope", 0.0))
        if features.get("event_proximity", 0.0) >= self.event_gate:
            return "MACRO_EVENT"
        if vol_ratio >= self.crisis_vol and drawdown <= self.crisis_drawdown:
            return "CRISIS"
        if vol_ratio >= self.vol_high:
            return "HIGH_VOL"
        if self.trend_strength(features) >= self.trend_bar and ti != 0.0:
            return "TREND_UP" if ti > 0 else "TREND_DOWN"
        if vol_ratio <= self.vol_low:
            return "LOW_VOL"
        return "RANGE"

    def _evidence(self, features: dict[str, float], label: str) -> list[Evidence]:
        """Signed evidence explaining the call (I4)."""
        adx = features.get("adx", 0.0)
        er = features.get("efficiency_ratio", 0.0)
        ti = features.get("trend_intensity", 0.0)
        vol_ratio = features.get("vol_ratio", 1.0)
        drawdown = features.get("drawdown", 0.0)
        proximity = features.get("event_proximity", 0.0)
        hurst = features.get("hurst", 0.5)

        character = "persistent" if hurst > 0.55 else "mean-reverting" if hurst < 0.45 else "random"
        evidence = [
            Evidence(
                name="trend_strength",
                detail=(
                    f"ADX {adx:.0f}, efficiency ratio {er:.2f}, "
                    f"drift/noise {ti:+.2f} → composite {self.trend_strength(features):.2f}"
                ),
                impact=float(np.clip(ti, -1.0, 1.0)),
                value=self.trend_strength(features),
            ),
            Evidence(
                name="volatility_regime",
                detail=f"realised vol is {vol_ratio:.2f}x its own median",
                impact=-_clip01((vol_ratio - 1.0) / 2.0),
                value=vol_ratio,
            ),
            Evidence(
                name="range_character",
                detail=f"Hurst exponent {hurst:.2f} ({character})",
                impact=0.0,
                value=hurst,
            ),
        ]
        if drawdown < -0.05:
            evidence.append(
                Evidence(
                    name="drawdown",
                    detail=f"price is {drawdown:.1%} off its running peak",
                    impact=float(np.clip(drawdown / 0.5, -1.0, 0.0)),
                    value=drawdown,
                )
            )
        if proximity > 0.0:
            evidence.append(
                Evidence(
                    name="event_proximity",
                    detail=f"macro-event proximity {proximity:.2f} "
                    f"({'inside' if proximity >= self.event_gate else 'outside'} the caution gate)",
                    impact=-proximity,
                    value=proximity,
                )
            )
        return evidence

    def state_from_features(
        self, features: dict[str, float], as_of: str = ""
    ) -> RegimeState:
        """Build the full :class:`RegimeState` from a point-in-time feature dict."""
        label = self.cascade(features)
        scores = {name: max(score, 0.01) for name, score in self.scores(features).items()}
        top = max(scores.values())
        if scores[label] < top:  # the hierarchy is authoritative
            scores[label] = top * 1.05
        total = sum(scores.values())
        probabilities = {name: score / total for name, score in scores.items()}
        return RegimeState(
            label=label,
            probabilities=probabilities,
            features=dict(features),
            evidence=self._evidence(features, label),
            tradeable=label not in self.untradeable,
            as_of=as_of,
            classifier=self.name,
        )

    def classify(self, snapshot: MarketSnapshot) -> RegimeState:
        """Classify a snapshot's market state (deterministic, I8; causal, I2)."""
        return self.state_from_features(snapshot_regime_features(snapshot), as_of=snapshot.as_of)


class _MixtureRegimeClassifier(RuleRegimeClassifier):
    """Shared machinery for the optional [ml] backends.

    Fits a component model (GMM / HMM) over the causal regime feature frame,
    then maps each learned component to a regime label by running the rule
    cascade on the component's mean feature vector — the statistical model
    finds the states, the rule engine names them (explainability preserved).
    """

    #: feature-frame columns fed to the component model.
    _COLUMNS = ("trend_intensity", "efficiency_ratio", "vol_ratio", "drawdown", "adx")

    def __init__(self, n_components: int = 4, seed: int = 42, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.n_components = n_components
        self.seed = seed
        self._model: Any = None
        self._component_labels: list[str] = []

    def _matrix(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        frame = regime_feature_frame(ohlcv)[list(self._COLUMNS)]
        return frame.dropna()

    def _build_model(self) -> Any:  # pragma: no cover - requires [ml]
        raise NotImplementedError

    def _component_probabilities(
        self, model: Any, row: np.ndarray
    ) -> np.ndarray:  # pragma: no cover - requires [ml]
        raise NotImplementedError

    def _component_means(self, model: Any) -> np.ndarray:  # pragma: no cover - requires [ml]
        return np.asarray(model.means_)

    def fit(self, ohlcv: pd.DataFrame) -> _MixtureRegimeClassifier:
        """Fit the component model and name each component via the rule cascade."""
        matrix = self._matrix(ohlcv)
        model = self._build_model()
        model.fit(matrix.to_numpy())
        self._model = model
        self._component_labels = []
        for mean in self._component_means(model):
            features = dict(zip(self._COLUMNS, (float(v) for v in mean), strict=True))
            self._component_labels.append(self.cascade(features))
        return self

    def classify(self, snapshot: MarketSnapshot) -> RegimeState:
        """Classify via the fitted components (fits on the snapshot when cold)."""
        features = snapshot_regime_features(snapshot)
        if features.get("event_proximity", 0.0) >= self.event_gate:
            # the calendar overrides any statistical state (BUILD_PLAN WP-4.3)
            return self.state_from_features(features, as_of=snapshot.as_of)
        if self._model is None:
            self.fit(snapshot.ohlcv)
        row = np.array([[features[c] for c in self._COLUMNS]], dtype=float)
        weights = self._component_probabilities(self._model, row)

        probabilities = {name: 0.0 for name in REGIME_LABELS}
        for weight, label in zip(weights, self._component_labels, strict=True):
            probabilities[label] += float(weight)
        total = sum(probabilities.values()) or 1.0
        probabilities = {name: p / total for name, p in probabilities.items()}
        label = max(REGIME_LABELS, key=lambda name: probabilities[name])

        evidence = self._evidence(features, label)
        evidence.append(
            Evidence(
                name="component_model",
                detail=(
                    f"{type(self).__name__}: {self.n_components} learned components "
                    f"named by the rule cascade as {sorted(set(self._component_labels))}"
                ),
                impact=0.0,
                value=float(probabilities[label]),
            )
        )
        return RegimeState(
            label=label,
            probabilities=probabilities,
            features=features,
            evidence=evidence,
            tradeable=label not in self.untradeable,
            as_of=snapshot.as_of,
            classifier=type(self).__name__,
        )


class GmmRegimeClassifier(_MixtureRegimeClassifier):
    """Gaussian-mixture regime classifier (``[ml]`` extra, lazy scikit-learn)."""

    name = "GmmRegimeClassifier"

    def _build_model(self) -> Any:
        try:
            from sklearn.mixture import GaussianMixture  # noqa: PLC0415 — [ml] extra
        except ImportError as exc:
            raise ImportError(
                "GmmRegimeClassifier requires scikit-learn — install the 'ml' extra "
                "(pip install quantos[ml]) or use the RuleRegimeClassifier baseline"
            ) from exc
        return GaussianMixture(n_components=self.n_components, random_state=self.seed)

    def _component_probabilities(self, model: Any, row: np.ndarray) -> np.ndarray:
        return np.asarray(model.predict_proba(row))[0]  # pragma: no cover - requires [ml]


class HmmRegimeClassifier(_MixtureRegimeClassifier):
    """Hidden-Markov regime classifier (``[ml]`` extra, lazy hmmlearn)."""

    name = "HmmRegimeClassifier"

    def _build_model(self) -> Any:
        try:
            from hmmlearn.hmm import GaussianHMM  # noqa: PLC0415 — [ml] extra
        except ImportError as exc:
            raise ImportError(
                "HmmRegimeClassifier requires hmmlearn — install the 'ml' extra "
                "(pip install quantos[ml]) or use the RuleRegimeClassifier baseline"
            ) from exc
        return GaussianHMM(n_components=self.n_components, random_state=self.seed)

    def _component_probabilities(
        self, model: Any, row: np.ndarray
    ) -> np.ndarray:  # pragma: no cover - requires [ml]
        return np.asarray(model.predict_proba(row))[0]
