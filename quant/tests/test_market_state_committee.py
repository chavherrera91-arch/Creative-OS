"""WP-4.4 — regime + anomalies in the committee: gate, record, explanation (I4/I5)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.anomaly.detectors import ZScoreDetector
from quantos.committee.analysts import AnomalyAnalyst
from quantos.committee.base import Direction
from quantos.committee.committee import default_committee, regime_aware_committee
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import decision_report, explain_decision
from quantos.regime.classifier import RuleRegimeClassifier


def snap(ohlcv: pd.DataFrame, **channels: object) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)  # type: ignore[arg-type]


def with_last_bar_volume_spike(ohlcv: pd.DataFrame, mult: float = 30.0) -> pd.DataFrame:
    out = ohlcv.copy()
    out.iloc[-1, out.columns.get_loc("volume")] *= mult
    return out


@pytest.fixture()
def crash_ohlcv() -> pd.DataFrame:
    return pd.concat(
        [
            make_ohlcv(n=150, drift=0.001, vol=0.004, seed=5),
            make_ohlcv(n=60, drift=-0.02, vol=0.03, seed=6, start="2024-01-07 06:00"),
        ]
    )


class TestAnomalyAnalyst:
    def test_abstains_when_the_tape_is_clean(self, ohlcv: pd.DataFrame) -> None:
        opinion = AnomalyAnalyst().analyze(snap(ohlcv))
        assert opinion.abstained
        assert opinion.direction is Direction.FLAT

    def test_flags_an_active_anomaly_direction_neutral(self, ohlcv: pd.DataFrame) -> None:
        opinion = AnomalyAnalyst().analyze(snap(with_last_bar_volume_spike(ohlcv)))
        assert not opinion.abstained
        assert opinion.direction is Direction.FLAT  # caution, not a side
        assert opinion.confidence > 0.0
        assert any(e.name == "anomaly_volume_spike" for e in opinion.evidence)
        assert all(e.impact == 0.0 for e in opinion.evidence)

    def test_prefers_the_context_summary_when_supplied(self, ohlcv: pd.DataFrame) -> None:
        summary = {
            "active": True,
            "score": 9.0,
            "threshold": 4.0,
            "kinds": {"gap": {"score": 9.0, "flag": True}},
        }
        opinion = AnomalyAnalyst().analyze(snap(ohlcv), context={"anomalies": summary})
        assert not opinion.abstained
        assert any(e.name == "anomaly_gap" for e in opinion.evidence)


class TestRegimeInTheDecision:
    """I4: the classified regime is part of the auditable record."""

    def test_decision_records_the_classified_regime(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = regime_aware_committee().deliberate(snap(uptrend_ohlcv))
        assert decision.regime["label"] == "TREND_UP"
        assert decision.regime["classifier"] == "RuleRegimeClassifier"
        assert decision.regime["evidence"], "regime evidence must be recorded (I4)"
        assert decision.as_dict()["regime"]["label"] == "TREND_UP"
        json.dumps(decision.as_dict())

    def test_caller_supplied_regime_wins_over_the_classifier(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        supplied = {"label": "RANGE", "tradeable": True}
        decision = regime_aware_committee().deliberate(
            snap(uptrend_ohlcv), context={"regime": supplied}
        )
        assert decision.regime == supplied

    def test_untradeable_regime_stands_the_committee_down(
        self, crash_ohlcv: pd.DataFrame
    ) -> None:
        """The regime gate fires before anything else (ARCHITECTURE §3)."""
        decision = regime_aware_committee().deliberate(snap(crash_ohlcv))
        assert decision.regime["label"] == "CRISIS"
        assert decision.regime["tradeable"] is False
        assert not decision.approved
        assert decision.direction is Direction.FLAT
        assert not decision.blocked_by_risk  # the gate, not the veto, stood us down
        assert any("regime gate" in reason for reason in decision.reasons)

    def test_regime_surfaces_in_explain_decision(self, crash_ohlcv: pd.DataFrame) -> None:
        narrative = explain_decision(regime_aware_committee().deliberate(snap(crash_ohlcv)))
        assert "REGIME" in narrative
        assert "CRISIS" in narrative
        assert "regime gate" in narrative


class TestAnomaliesInTheDecision:
    """Acceptance: an active anomaly surfaces in explain_decision (I4)."""

    def test_decision_records_active_anomalies(self, ohlcv: pd.DataFrame) -> None:
        spiked = with_last_bar_volume_spike(ohlcv)
        decision = regime_aware_committee().deliberate(snap(spiked))
        assert decision.anomalies["active"] is True
        assert decision.anomalies["kinds"]["volume_spike"]["flag"] is True
        assert decision.as_dict()["anomalies"]["active"] is True

    def test_active_anomaly_surfaces_in_the_narrative(self, ohlcv: pd.DataFrame) -> None:
        decision = regime_aware_committee().deliberate(snap(with_last_bar_volume_spike(ohlcv)))
        narrative = explain_decision(decision)
        assert "ANOMALIES" in narrative
        assert "volume spike" in narrative
        assert any("anomaly noted" in reason for reason in decision.reasons)
        json.dumps(decision_report(decision))

    def test_quiet_tape_is_recorded_as_inactive(self, ohlcv: pd.DataFrame) -> None:
        decision = regime_aware_committee().deliberate(snap(ohlcv))
        assert decision.anomalies["active"] is False
        assert "no active anomalies" in explain_decision(decision)


class TestHierarchyAndGuards:
    """The M1 guarantees survive the M4 layer."""

    def test_risk_veto_still_absolute_in_a_tradeable_regime(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        decision = regime_aware_committee().deliberate(
            snap(uptrend_ohlcv), context={"daily_pnl_pct": -0.10}
        )
        assert decision.blocked_by_risk  # I5: one veto forces FLAT
        assert decision.direction is Direction.FLAT
        assert not decision.approved

    def test_regime_gate_outranks_the_risk_veto_in_the_reasons(
        self, crash_ohlcv: pd.DataFrame
    ) -> None:
        decision = regime_aware_committee().deliberate(
            snap(crash_ohlcv), context={"daily_pnl_pct": -0.10}
        )
        assert any("regime gate" in reason for reason in decision.reasons)
        assert not decision.blocked_by_risk  # gate fired first (§3 hierarchy)

    def test_default_committee_is_unchanged(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """Back-compat: without M4 wiring there is no regime and no anomalies."""
        decision = default_committee().deliberate(snap(uptrend_ohlcv))
        assert decision.regime == {}
        assert decision.anomalies == {}

    def test_manifest_pins_the_market_state_components(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        decision = regime_aware_committee().deliberate(snap(uptrend_ohlcv))
        assert decision.run_manifest["regime_classifier"] == "RuleRegimeClassifier"
        assert decision.run_manifest["anomaly_detector"] == "ZScoreDetector"

    def test_deliberation_is_reproducible(
        self, uptrend_ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        committee = regime_aware_committee(
            regime_classifier=RuleRegimeClassifier(), anomaly_detector=ZScoreDetector()
        )
        assert_reproducible(committee.deliberate, snap(uptrend_ohlcv))
