"""WP-1.6 — explainability: narrative + serialisable report (I4)."""

from __future__ import annotations

import json

import pandas as pd

from quantos.committee.committee import default_committee
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import decision_report, explain_decision


def bullish_snapshot(ohlcv: pd.DataFrame, **overrides: object) -> MarketSnapshot:
    channels: dict[str, object] = {
        "macro": {"dxy_trend": -0.9, "risk_appetite": 0.9},
        "sentiment": {"score": 0.6},
    }
    channels.update(overrides)
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)  # type: ignore[arg-type]


class TestNarrative:
    def test_contains_all_sections(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        text = explain_decision(decision)
        for section in (
            "DECISION",
            "CONFIDENCE",
            "REASONS FOR",
            "REASONS AGAINST",
            "RISKS",
            "ANALYST PANEL",
            "CHAIR",
        ):
            assert section in text, f"missing section {section}"
        assert "BTC/USDT" in text

    def test_surfaces_a_veto(self, uptrend_ohlcv: pd.DataFrame) -> None:
        snap = bullish_snapshot(
            uptrend_ohlcv, events=[{"name": "emergency FOMC", "impact": "high"}]
        )
        decision = default_committee().deliberate(snap)
        text = explain_decision(decision)
        assert "BLOCKED BY RISK VETO" in text
        assert "VETO" in text
        assert "emergency FOMC" in text

    def test_surfaces_abstentions(self, ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(MarketSnapshot("BTC/USDT", "1h", ohlcv))
        text = explain_decision(decision)
        assert "ABSTAINED" in text  # macro/sentiment/onchain have no data (I3)


class TestReport:
    def test_json_serialisable(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        report = decision_report(decision)
        json.dumps(report)  # I4
        assert report["decision"]["symbol"] == "BTC/USDT"
        assert report["narrative"] == explain_decision(decision)

    def test_veto_flag_and_reason_split(self, uptrend_ohlcv: pd.DataFrame) -> None:
        snap = bullish_snapshot(uptrend_ohlcv, events=[{"name": "FOMC", "impact": "high"}])
        report = decision_report(default_committee().deliberate(snap))
        assert report["vetoed"] is True
        assert not report["stood_down"]
        assert all(e["impact"] > 0 for e in report["reasons_for"])
        assert all(e["impact"] < 0 for e in report["reasons_against"])
        # strongest evidence first
        impacts = [e["impact"] for e in report["reasons_for"]]
        assert impacts == sorted(impacts, reverse=True)

    def test_stand_down_flag(self, ohlcv: pd.DataFrame) -> None:
        committee = default_committee()
        committee.confidence_model.threshold = 0.99
        report = decision_report(committee.deliberate(bullish_snapshot(ohlcv)))
        assert report["stood_down"] is True
        assert report["vetoed"] is False
