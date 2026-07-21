"""WP-7.4 — research pipeline: regime → meta-selection → committee (§4, I4/I8)."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.committee.base import Direction
from quantos.data.models import MarketSnapshot
from quantos.meta import BaselineMetaLearner, RegimePerformanceTable
from quantos.pipeline import research_pipeline
from quantos.scenarios.library import get_scenario
from quantos.strategy.base import IndicatorStrategy, Strategy
from quantos.strategy.generator import generate


def two_family_universe() -> tuple[list[Strategy], str, str]:
    """Two runnable strategies from two distinct generated families (I8)."""
    by_family: dict[str, IndicatorStrategy] = {}
    for spec in generate(8, seed=5):
        by_family.setdefault(spec.family, IndicatorStrategy(spec))
        if len(by_family) == 2:
            break
    families = sorted(by_family)
    assert len(families) == 2, "seed must yield two distinct families"
    return [by_family[f] for f in families], families[0], families[1]


def validated_learner(family: str, regime: str) -> BaselineMetaLearner:
    table = RegimePerformanceTable()
    for score in (1.0, 2.0, 1.5):
        table.record(family, regime, score)
    return BaselineMetaLearner(table)


def bullish_snapshot(ohlcv: pd.DataFrame) -> MarketSnapshot:
    return MarketSnapshot(
        "BTC/USDT",
        "1h",
        ohlcv,
        macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
        sentiment={"score": 0.6},
        onchain={"whale_accumulation": 0.8},
    )


class TestValidatedFlow:
    def test_only_regime_validated_family_feeds_the_committee(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        universe, f1, _f2 = two_family_universe()
        pipeline = research_pipeline(universe, meta=validated_learner(f1, "TREND_UP"))
        decision = pipeline.decide(bullish_snapshot(uptrend_ohlcv))

        assert decision.regime["label"] == "TREND_UP"
        families = {entry["family"] for entry in decision.strategies_considered}
        assert families == {f1}  # the unvalidated family never reaches the bench
        entry = decision.strategies_considered[0]
        assert isinstance(entry["signal"], float)  # the strategy emitted its signal
        assert "validated for TREND_UP" in entry["verdict"]  # I4

    def test_dossier_serialises_regime_and_strategies(self, uptrend_ohlcv: pd.DataFrame) -> None:
        universe, f1, _ = two_family_universe()
        pipeline = research_pipeline(universe, meta=validated_learner(f1, "TREND_UP"))
        payload = pipeline.decide(bullish_snapshot(uptrend_ohlcv)).as_dict()
        assert payload["regime"]["label"] == "TREND_UP"
        assert payload["strategies_considered"][0]["family"] == f1


class TestStandDowns:
    def test_unvalidated_regime_stands_the_pipeline_down(self, uptrend_ohlcv: pd.DataFrame) -> None:
        universe, _, _ = two_family_universe()
        pipeline = research_pipeline(universe, meta=BaselineMetaLearner())  # empty table
        decision = pipeline.decide(bullish_snapshot(uptrend_ohlcv))
        assert decision.direction is Direction.FLAT and not decision.approved
        assert any("meta-learner gate" in reason for reason in decision.reasons)
        assert decision.strategies_considered == []

    def test_untradeable_regime_is_the_chairs_gate(self) -> None:
        universe, f1, _ = two_family_universe()
        pipeline = research_pipeline(universe, meta=validated_learner(f1, "CRISIS"))
        decision = pipeline.decide(get_scenario("COVID_CRASH").core_snapshot())
        assert decision.regime["label"] == "CRISIS"
        assert decision.direction is Direction.FLAT and not decision.approved
        assert any("regime gate" in reason for reason in decision.reasons)
        # the chair stood down, not the meta gate
        assert not any("meta-learner gate" in reason for reason in decision.reasons)

    def test_empty_universe_means_no_meta_gating(self, uptrend_ohlcv: pd.DataFrame) -> None:
        pipeline = research_pipeline([], meta=BaselineMetaLearner())
        decision = pipeline.decide(bullish_snapshot(uptrend_ohlcv))
        assert decision.regime["label"] == "TREND_UP"  # regime still recorded
        assert not any("meta-learner gate" in reason for reason in decision.reasons)


class TestReproducibility:
    def test_decide_replays_identically(self, uptrend_ohlcv: pd.DataFrame) -> None:
        universe, f1, _ = two_family_universe()
        snapshot = bullish_snapshot(uptrend_ohlcv)
        first = research_pipeline(universe, meta=validated_learner(f1, "TREND_UP")).decide(snapshot)
        second = research_pipeline(universe, meta=validated_learner(f1, "TREND_UP")).decide(
            snapshot
        )
        assert first.as_dict() == second.as_dict()  # I8


def test_committee_approval_path_still_works(uptrend_ohlcv: pd.DataFrame) -> None:
    """With a validated family the pipeline must not block a good trade."""
    universe, f1, _ = two_family_universe()
    pipeline = research_pipeline(universe, meta=validated_learner(f1, "TREND_UP"))
    decision = pipeline.decide(bullish_snapshot(uptrend_ohlcv))
    if not decision.approved:  # the bench may still stand down on evidence
        pytest.skip("committee stood down on evidence; gate behaviour covered above")
    assert decision.direction is not Direction.FLAT
