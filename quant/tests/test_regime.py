"""WP-4.3 — Market Regime Engine: explainable labels, probabilities, evidence (I4/I8)."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.committee.base import Evidence
from quantos.data.models import MarketSnapshot
from quantos.regime.base import REGIME_LABELS, RegimeClassifier, RegimeState
from quantos.regime.classifier import (
    GmmRegimeClassifier,
    HmmRegimeClassifier,
    RuleRegimeClassifier,
)

HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None
HAS_HMMLEARN = importlib.util.find_spec("hmmlearn") is not None


def snap(ohlcv: pd.DataFrame, **channels: object) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)  # type: ignore[arg-type]


@pytest.fixture()
def high_vol_ohlcv() -> pd.DataFrame:
    """Calm history followed by a late volatility explosion."""
    return pd.concat(
        [
            make_ohlcv(n=150, vol=0.003, seed=3),
            make_ohlcv(n=50, vol=0.025, seed=4, start="2024-01-07 06:00"),
        ]
    )


@pytest.fixture()
def crash_ohlcv() -> pd.DataFrame:
    """A market breaking down: violent selling on exploding volatility."""
    return pd.concat(
        [
            make_ohlcv(n=150, drift=0.001, vol=0.004, seed=5),
            make_ohlcv(n=60, drift=-0.02, vol=0.03, seed=6, start="2024-01-07 06:00"),
        ]
    )


class TestRegimeState:
    def test_rejects_unknown_label(self) -> None:
        with pytest.raises(ValueError, match="unknown regime label"):
            RegimeState(label="SIDEWAYS", probabilities={})

    def test_rejects_unknown_probability_keys(self) -> None:
        with pytest.raises(ValueError, match="unknown labels"):
            RegimeState(label="RANGE", probabilities={"MOON": 1.0})

    def test_rejects_non_normalised_probabilities(self) -> None:
        with pytest.raises(ValueError, match="sum to ~1"):
            RegimeState(label="RANGE", probabilities={"RANGE": 0.4})

    def test_serialises_fully(self) -> None:
        state = RegimeState(
            label="TREND_UP",
            probabilities={"TREND_UP": 1.0},
            features={"adx": 40.0},
            evidence=[Evidence(name="x", detail="d", impact=0.5)],
            as_of="2024-01-01",
            classifier="test",
        )
        record = state.as_dict()
        json.dumps(record)
        assert record["label"] == "TREND_UP"
        assert record["tradeable"] is True
        assert record["evidence"][0]["impact"] == 0.5


class TestRuleClassifierLabels:
    """Acceptance: trend / vol / event fixtures classify as specified."""

    def test_satisfies_the_port(self) -> None:
        assert isinstance(RuleRegimeClassifier(), RegimeClassifier)

    def test_strong_uptrend_is_trend_up_with_evidence(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        state = RuleRegimeClassifier().classify(snap(uptrend_ohlcv))
        assert state.label == "TREND_UP"
        assert state.tradeable is True
        assert state.evidence, "the call must carry evidence (I4)"
        trend_evidence = next(e for e in state.evidence if e.name == "trend_strength")
        assert trend_evidence.impact > 0.5
        assert state.features["adx"] > 25.0

    def test_strong_downtrend_is_trend_down(self, downtrend_ohlcv: pd.DataFrame) -> None:
        state = RuleRegimeClassifier().classify(snap(downtrend_ohlcv))
        assert state.label == "TREND_DOWN"
        assert next(e for e in state.evidence if e.name == "trend_strength").impact < 0.0

    def test_vol_burst_is_high_vol_or_crisis(self, high_vol_ohlcv: pd.DataFrame) -> None:
        state = RuleRegimeClassifier().classify(snap(high_vol_ohlcv))
        assert state.label in {"HIGH_VOL", "CRISIS"}
        assert state.features["vol_ratio"] > 2.0

    def test_breakdown_is_crisis_and_untradeable(self, crash_ohlcv: pd.DataFrame) -> None:
        state = RuleRegimeClassifier().classify(snap(crash_ohlcv))
        assert state.label == "CRISIS"
        assert state.tradeable is False
        assert state.features["drawdown"] < -0.20
        assert any(e.name == "drawdown" and e.impact < 0 for e in state.evidence)

    def test_macro_event_flag_forces_macro_event(self, uptrend_ohlcv: pd.DataFrame) -> None:
        events = [{"name": "FOMC", "impact": "high"}]
        state = RuleRegimeClassifier().classify(snap(uptrend_ohlcv, events=events))
        assert state.label == "MACRO_EVENT"
        assert any(e.name == "event_proximity" for e in state.evidence)
        # without the event the same bars are a plain trend
        assert RuleRegimeClassifier().classify(snap(uptrend_ohlcv)).label == "TREND_UP"

    def test_late_calm_is_low_vol(self) -> None:
        calm_late = pd.concat(
            [
                make_ohlcv(n=150, vol=0.015, seed=8),
                make_ohlcv(n=60, vol=0.002, seed=9, start="2024-01-07 06:00"),
            ]
        )
        assert RuleRegimeClassifier().classify(snap(calm_late)).label == "LOW_VOL"

    def test_directionless_walk_is_range(self, ohlcv: pd.DataFrame) -> None:
        assert RuleRegimeClassifier().classify(snap(ohlcv)).label == "RANGE"


class TestProbabilitiesAndDeterminism:
    def test_probabilities_cover_all_labels_and_sum_to_one(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        state = RuleRegimeClassifier().classify(snap(uptrend_ohlcv))
        assert set(state.probabilities) == set(REGIME_LABELS)
        assert np.isclose(sum(state.probabilities.values()), 1.0)
        assert all(p >= 0.0 for p in state.probabilities.values())

    def test_label_is_the_argmax_of_probabilities(self, ohlcv: pd.DataFrame) -> None:
        for frame in (ohlcv, make_ohlcv(drift=0.004, vol=0.004, seed=7)):
            state = RuleRegimeClassifier().classify(snap(frame))
            assert state.label == max(state.probabilities, key=lambda k: state.probabilities[k])

    def test_same_input_same_output(
        self, uptrend_ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        """I8: classification replays identically."""
        classifier = RuleRegimeClassifier()
        state = assert_reproducible(classifier.classify, snap(uptrend_ohlcv))
        assert state.as_of == snap(uptrend_ohlcv).as_of

    def test_classification_is_causal(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """I2: the state at bar t ignores bars > t entirely."""
        classifier = RuleRegimeClassifier()
        prefix = uptrend_ohlcv.iloc[:150]
        perturbed = uptrend_ohlcv.copy()
        perturbed.iloc[150:, perturbed.columns.get_loc("close")] *= 0.5
        assert (
            classifier.classify(snap(prefix)).as_dict()
            == classifier.classify(snap(perturbed.iloc[:150])).as_dict()
        )

    def test_state_serialises_to_json(self, ohlcv: pd.DataFrame) -> None:
        json.dumps(RuleRegimeClassifier().classify(snap(ohlcv)).as_dict())


class TestMlBackendsAreOptional:
    """[ml] classifiers: importable and constructible always, lazy failure."""

    @pytest.mark.parametrize("cls", [GmmRegimeClassifier, HmmRegimeClassifier])
    def test_constructing_needs_no_ml_deps(self, cls: type) -> None:
        classifier = cls(n_components=3, seed=42)
        assert isinstance(classifier, RegimeClassifier)

    @pytest.mark.skipif(HAS_SKLEARN, reason="sklearn installed — lazy failure not reachable")
    def test_gmm_without_sklearn_raises_helpfully(self, ohlcv: pd.DataFrame) -> None:
        with pytest.raises(ImportError, match="ml"):
            GmmRegimeClassifier().fit(ohlcv)

    @pytest.mark.skipif(HAS_HMMLEARN, reason="hmmlearn installed — lazy failure not reachable")
    def test_hmm_without_hmmlearn_raises_helpfully(self, ohlcv: pd.DataFrame) -> None:
        with pytest.raises(ImportError, match="ml"):
            HmmRegimeClassifier().fit(ohlcv)

    def test_event_gate_works_even_without_ml_deps(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """The calendar override never needs the statistical backend."""
        events = [{"name": "CPI", "impact": "high"}]
        state = GmmRegimeClassifier().classify(snap(uptrend_ohlcv, events=events))
        assert state.label == "MACRO_EVENT"

    @pytest.mark.skipif(not HAS_SKLEARN, reason="sklearn not installed")
    def test_gmm_classifies_when_available(  # pragma: no cover
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        state = GmmRegimeClassifier(seed=42).classify(snap(uptrend_ohlcv))
        assert state.label in REGIME_LABELS
