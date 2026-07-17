"""WP-1.5 — risk veto absolute (I5), chair hierarchy, auditable decision (I4)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.committee.base import Direction
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.committee.risk_manager import RiskManager
from quantos.data.models import MarketSnapshot


def bullish_snapshot(ohlcv: pd.DataFrame, **overrides: Any) -> MarketSnapshot:
    """A snapshot every analyst loves: strong uptrend + supportive channels."""
    channels: dict[str, Any] = {
        "macro": {"dxy_trend": -0.9, "rates_trend": -0.5, "risk_appetite": 0.9},
        "sentiment": {"score": 0.6},
        "onchain": {"net_exchange_flow": -1_500.0, "whale_accumulation": 0.8},
    }
    channels.update(overrides)
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)


class TestRiskRules:
    def test_clean_market_passes(self, uptrend_ohlcv: pd.DataFrame) -> None:
        assessment = RiskManager().assess(bullish_snapshot(uptrend_ohlcv))
        assert not assessment.vetoed
        assert assessment.approved

    def test_volatility_spike_vetoes(self) -> None:
        calm = make_ohlcv(n=180, vol=0.002, seed=11)
        spike = make_ohlcv(n=40, vol=0.06, seed=12)
        spike.index = pd.date_range(
            calm.index[-1] + pd.Timedelta(hours=1), periods=40, freq="1h", tz="UTC"
        )
        df = pd.concat([calm, spike])
        assessment = RiskManager().assess(MarketSnapshot("BTC/USDT", "1h", df))
        assert any("volatility spike" in v for v in assessment.vetoes)

    def test_high_impact_macro_event_vetoes(self, ohlcv: pd.DataFrame) -> None:
        snap = MarketSnapshot("BTC/USDT", "1h", ohlcv, events=[{"name": "FOMC", "impact": "high"}])
        assessment = RiskManager().assess(snap)
        assert assessment.vetoed
        assert any("FOMC" in v for v in assessment.vetoes)

    def test_medium_event_only_warns(self, ohlcv: pd.DataFrame) -> None:
        snap = MarketSnapshot("BTC/USDT", "1h", ohlcv, events=[{"name": "CPI", "impact": "medium"}])
        assessment = RiskManager().assess(snap)
        assert not assessment.vetoed
        assert any("CPI" in w for w in assessment.warnings)

    def test_daily_drawdown_vetoes_via_context(self, ohlcv: pd.DataFrame) -> None:
        assessment = RiskManager(max_daily_drawdown=0.05).assess(
            MarketSnapshot("BTC/USDT", "1h", ohlcv), context={"daily_pnl_pct": -0.08}
        )
        assert any("daily loss" in v for v in assessment.vetoes)

    def test_low_liquidity_vetoes(self, ohlcv: pd.DataFrame) -> None:
        df = ohlcv.copy()
        df.iloc[-25:, df.columns.get_loc("volume")] = 0.5  # volume collapse
        assessment = RiskManager().assess(MarketSnapshot("BTC/USDT", "1h", df))
        assert any("liquidity" in v for v in assessment.vetoes)

    def test_assessment_serialisable(self, ohlcv: pd.DataFrame) -> None:
        assessment = RiskManager().assess(MarketSnapshot("BTC/USDT", "1h", ohlcv))
        report = assessment.as_dict()
        json.dumps(report)
        assert len(report["checks"]) == 4  # every rule recorded, passes included


class TestChairHierarchy:
    def test_unanimous_long_is_approved_when_clean(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        assert decision.approved
        assert decision.direction is Direction.LONG
        assert not decision.blocked_by_risk
        assert decision.confidence > 0.35

    def test_single_veto_blocks_unanimous_long(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """I5: one veto forces FLAT regardless of confidence."""
        snap = bullish_snapshot(
            uptrend_ohlcv, events=[{"name": "emergency FOMC", "impact": "high"}]
        )
        decision = default_committee().deliberate(snap)
        assert decision.direction is Direction.FLAT
        assert not decision.approved
        assert decision.blocked_by_risk
        assert decision.confidence > 0.35  # conviction was there — the veto still wins
        assert any("veto" in r for r in decision.reasons)

    def test_below_threshold_stands_down(self, ohlcv: pd.DataFrame) -> None:
        committee = default_committee()
        committee.confidence_model.threshold = 0.99  # unreachable bar
        decision = committee.deliberate(bullish_snapshot(ohlcv))
        assert not decision.approved
        assert decision.direction is Direction.FLAT
        assert not decision.blocked_by_risk
        assert any("standing down" in r for r in decision.reasons)

    def test_regime_gate_precedes_everything(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(
            bullish_snapshot(uptrend_ohlcv),
            context={"regime": {"label": "CRISIS", "tradeable": False}},
        )
        assert not decision.approved
        assert decision.direction is Direction.FLAT
        assert not decision.blocked_by_risk  # gated by regime, not by a veto
        assert any("regime gate" in r for r in decision.reasons)
        assert decision.regime["label"] == "CRISIS"


class TestDecisionRecord:
    def test_serialises_fully(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        record = decision.as_dict()
        json.dumps(record)  # I4: complete and JSON-serialisable
        assert set(record) >= {
            "symbol",
            "timeframe",
            "price",
            "direction",
            "approved",
            "confidence",
            "blocked_by_risk",
            "reasons",
            "opinions",
            "confidence_report",
            "risk",
            "regime",
            "strategies_considered",
            "run_manifest",
        }
        assert record["regime"] == {}  # M1: defaults empty, fields present (I7)
        assert record["strategies_considered"] == []
        manifest = record["run_manifest"]
        assert manifest["seed"] == 42
        assert manifest["analysts"]  # enough to replay (I8)

    def test_deliberation_is_reproducible(
        self,
        uptrend_ohlcv: pd.DataFrame,
        assert_reproducible: Callable[..., Any],
    ) -> None:
        committee = default_committee()
        snapshot = bullish_snapshot(uptrend_ohlcv)
        assert_reproducible(lambda: committee.deliberate(snapshot).as_dict())

    def test_committee_is_composable(self, ohlcv: pd.DataFrame) -> None:
        """I7: a custom bench plugs in without touching the core."""
        from quantos.committee.analysts import TechnicalAnalyst

        committee = InvestmentCommittee(analysts=[TechnicalAnalyst()])
        decision = committee.deliberate(MarketSnapshot("ETH/USDT", "1h", ohlcv))
        assert decision.symbol == "ETH/USDT"
        assert len(decision.opinions) == 1

    def test_price_is_last_close(self, ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(MarketSnapshot("BTC/USDT", "1h", ohlcv))
        assert decision.price == pytest.approx(float(np.asarray(ohlcv["close"])[-1]))
