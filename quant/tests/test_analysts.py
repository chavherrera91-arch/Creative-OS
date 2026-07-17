"""WP-1.3 — analyst behaviour: evidence-based opinions + honest abstention (I3)."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.committee.analysts import (
    MacroAnalyst,
    OnChainAnalyst,
    SentimentAnalyst,
    StatisticalAnalyst,
    TechnicalAnalyst,
    default_analysts,
)
from quantos.committee.base import AnalystOpinion, Direction, Evidence
from quantos.data.models import MarketSnapshot


def snap(ohlcv: pd.DataFrame, **channels: object) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)  # type: ignore[arg-type]


class TestCoreTypes:
    def test_direction_signs(self) -> None:
        assert Direction.LONG.sign == 1
        assert Direction.SHORT.sign == -1
        assert Direction.FLAT.sign == 0
        assert Direction.from_sign(0.5) is Direction.LONG
        assert Direction.from_sign(-0.5) is Direction.SHORT
        assert Direction.from_sign(0.1, dead_zone=0.15) is Direction.FLAT

    def test_evidence_impact_bounds(self) -> None:
        with pytest.raises(ValueError):
            Evidence(name="x", detail="too strong", impact=1.5)

    def test_abstained_opinion_cannot_claim_confidence(self) -> None:
        with pytest.raises(ValueError):
            AnalystOpinion(
                analyst="a", category="c", direction=Direction.FLAT, confidence=0.5, abstained=True
            )


class TestTechnicalAnalyst:
    def test_bullish_on_uptrend(self, uptrend_ohlcv: pd.DataFrame) -> None:
        opinion = TechnicalAnalyst().analyze(snap(uptrend_ohlcv))
        assert opinion.direction is Direction.LONG
        assert opinion.confidence > 0.2
        assert not opinion.abstained
        assert opinion.evidence

    def test_bearish_on_downtrend(self, downtrend_ohlcv: pd.DataFrame) -> None:
        opinion = TechnicalAnalyst().analyze(snap(downtrend_ohlcv))
        assert opinion.direction is Direction.SHORT

    def test_abstains_on_short_history(self) -> None:
        opinion = TechnicalAnalyst().analyze(snap(make_ohlcv(n=30)))
        assert opinion.abstained
        assert opinion.direction is Direction.FLAT
        assert opinion.confidence == 0.0


class TestStatisticalAnalyst:
    def test_emits_evidence(self, ohlcv: pd.DataFrame) -> None:
        opinion = StatisticalAnalyst().analyze(snap(ohlcv))
        assert not opinion.abstained
        names = {e.name for e in opinion.evidence}
        assert {"zscore_reversion", "short_momentum", "volatility_regime"} <= names

    def test_consumes_strategy_signal_context(self, ohlcv: pd.DataFrame) -> None:
        opinion = StatisticalAnalyst().analyze(snap(ohlcv), context={"strategy_signal": 0.9})
        assert any(e.name == "strategy_signal" for e in opinion.evidence)


class TestDataHungryAnalystsAbstainHonestly:
    """I3: no channel -> abstain; never fabricate conviction."""

    @pytest.mark.parametrize(
        "analyst_cls", [MacroAnalyst, SentimentAnalyst, OnChainAnalyst], ids=lambda c: c.__name__
    )
    def test_abstains_without_channel(self, analyst_cls: type, ohlcv: pd.DataFrame) -> None:
        opinion = analyst_cls().analyze(snap(ohlcv))
        assert opinion.abstained
        assert opinion.direction is Direction.FLAT
        assert opinion.confidence == 0.0
        assert opinion.evidence  # the abstention reason is itself recorded (I4)

    def test_macro_opines_with_data(self, ohlcv: pd.DataFrame) -> None:
        opinion = MacroAnalyst().analyze(
            snap(ohlcv, macro={"dxy_trend": -0.8, "rates_trend": -0.5, "risk_appetite": 0.7})
        )
        assert not opinion.abstained
        assert opinion.direction is Direction.LONG  # weak dollar + easing + risk-on

    def test_sentiment_contrarian_at_extremes(self, ohlcv: pd.DataFrame) -> None:
        opinion = SentimentAnalyst().analyze(snap(ohlcv, sentiment={"score": 0.95}))
        assert any(e.name == "sentiment_extreme" and e.impact < 0 for e in opinion.evidence)

    def test_onchain_bearish_on_exchange_inflows(self, ohlcv: pd.DataFrame) -> None:
        opinion = OnChainAnalyst().analyze(snap(ohlcv, onchain={"net_exchange_flow": 3_000.0}))
        assert opinion.direction is Direction.SHORT


class TestEveryOpinion:
    def test_all_default_analysts_return_valid_serialisable_opinions(
        self, ohlcv: pd.DataFrame
    ) -> None:
        snapshot = snap(ohlcv)
        for analyst in default_analysts():
            opinion = analyst.analyze(snapshot)
            assert opinion.evidence, f"{analyst.name} emitted no evidence"
            assert all(-1.0 <= e.impact <= 1.0 for e in opinion.evidence)
            json.dumps(opinion.as_dict())

    def test_deterministic(self, ohlcv: pd.DataFrame) -> None:
        snapshot = snap(ohlcv)
        for analyst in default_analysts():
            assert analyst.analyze(snapshot).as_dict() == analyst.analyze(snapshot).as_dict()
