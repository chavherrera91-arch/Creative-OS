"""WP-3.1 — composable risk limit library; RiskManager refactor stays back-compatible."""

from __future__ import annotations

import json

import pandas as pd
from conftest import make_ohlcv

from quantos.committee.risk_manager import RiskManager
from quantos.data.models import MarketSnapshot
from quantos.risk.limits import (
    OK,
    VETO,
    WARNING,
    CorrelationBreak,
    DailyDrawdown,
    LowLiquidity,
    MacroEvent,
    MaxPositionSize,
    RiskRule,
    VolatilitySpike,
    default_rules,
)


def snap(df: pd.DataFrame, **kwargs: object) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", df, **kwargs)  # type: ignore[arg-type]


class TestVolatilitySpike:
    def test_calm_market_ok(self, ohlcv: pd.DataFrame) -> None:
        assert VolatilitySpike().check(snap(ohlcv)).level == OK

    def test_spike_vetoes(self) -> None:
        calm = make_ohlcv(n=180, vol=0.002, seed=11)
        spike = make_ohlcv(n=40, vol=0.06, seed=12)
        spike.index = pd.date_range(
            calm.index[-1] + pd.Timedelta(hours=1), periods=40, freq="1h", tz="UTC"
        )
        check = VolatilitySpike().check(snap(pd.concat([calm, spike])))
        assert check.level == VETO
        assert "volatility spike" in check.message

    def test_warn_band(self) -> None:
        calm = make_ohlcv(n=180, vol=0.002, seed=11)
        spike = make_ohlcv(n=40, vol=0.06, seed=12)
        spike.index = pd.date_range(
            calm.index[-1] + pd.Timedelta(hours=1), periods=40, freq="1h", tz="UTC"
        )
        # A sky-high veto bar leaves only the warning band reachable.
        check = VolatilitySpike(max_ratio=1e9, warn_ratio=1.8).check(snap(pd.concat([calm, spike])))
        assert check.level == WARNING


class TestMacroEvent:
    def test_high_impact_vetoes(self, ohlcv: pd.DataFrame) -> None:
        check = MacroEvent().check(snap(ohlcv, events=[{"name": "FOMC", "impact": "high"}]))
        assert check.level == VETO
        assert "FOMC" in check.message

    def test_medium_impact_warns(self, ohlcv: pd.DataFrame) -> None:
        check = MacroEvent().check(snap(ohlcv, events=[{"name": "CPI", "impact": "medium"}]))
        assert check.level == WARNING

    def test_context_event_vetoes(self, ohlcv: pd.DataFrame) -> None:
        check = MacroEvent().check(snap(ohlcv), context={"macro_event": "emergency FOMC"})
        assert check.level == VETO

    def test_quiet_calendar_ok(self, ohlcv: pd.DataFrame) -> None:
        assert MacroEvent().check(snap(ohlcv)).level == OK


class TestDailyDrawdown:
    def test_breach_vetoes(self, ohlcv: pd.DataFrame) -> None:
        check = DailyDrawdown(0.05).check(snap(ohlcv), context={"daily_pnl_pct": -0.08})
        assert check.level == VETO
        assert "daily loss" in check.message

    def test_within_limit_ok(self, ohlcv: pd.DataFrame) -> None:
        assert DailyDrawdown(0.05).check(snap(ohlcv), context={"daily_pnl_pct": -0.02}).level == OK


class TestLowLiquidity:
    def test_collapse_vetoes(self, ohlcv: pd.DataFrame) -> None:
        df = ohlcv.copy()
        df.iloc[-25:, df.columns.get_loc("volume")] = 0.5
        check = LowLiquidity().check(snap(df))
        assert check.level == VETO
        assert "liquidity" in check.message

    def test_healthy_volume_ok(self, ohlcv: pd.DataFrame) -> None:
        assert LowLiquidity().check(snap(ohlcv)).level == OK


class TestCorrelationBreak:
    def test_no_benchmark_ok(self, ohlcv: pd.DataFrame) -> None:
        assert CorrelationBreak().check(snap(ohlcv)).level == OK

    def test_stable_correlation_ok(self, ohlcv: pd.DataFrame) -> None:
        benchmark = ohlcv["close"] * 2.0  # perfectly correlated throughout
        check = CorrelationBreak().check(snap(ohlcv), context={"benchmark_close": benchmark})
        assert check.level == OK

    def test_break_vetoes(self, ohlcv: pd.DataFrame) -> None:
        # Benchmark tracks the asset, then decouples to an anti-correlated tail.
        benchmark = ohlcv["close"].copy()
        tail = benchmark.iloc[-20:]
        benchmark.iloc[-20:] = 2.0 * float(tail.iloc[0]) - tail.values  # mirror the path
        check = CorrelationBreak(max_break=0.6, window=20).check(
            snap(ohlcv), context={"benchmark_close": benchmark}
        )
        assert check.level == VETO
        assert "correlation break" in check.message


class TestMaxPositionSize:
    def test_no_proposal_ok(self, ohlcv: pd.DataFrame) -> None:
        assert MaxPositionSize(0.25).check(snap(ohlcv)).level == OK

    def test_oversize_vetoes(self, ohlcv: pd.DataFrame) -> None:
        check = MaxPositionSize(0.25).check(
            snap(ohlcv), context={"proposed_position_fraction": 0.4}
        )
        assert check.level == VETO
        assert "exceeds" in check.message

    def test_short_side_counts_too(self, ohlcv: pd.DataFrame) -> None:
        check = MaxPositionSize(0.25).check(
            snap(ohlcv), context={"proposed_position_fraction": -0.4}
        )
        assert check.level == VETO

    def test_within_cap_ok(self, ohlcv: pd.DataFrame) -> None:
        check = MaxPositionSize(0.25).check(
            snap(ohlcv), context={"proposed_position_fraction": 0.2}
        )
        assert check.level == OK


class TestRiskManagerRefactor:
    def test_default_rules_match_m1_set(self) -> None:
        names = [r.name for r in default_rules()]
        assert names == ["volatility_spike", "macro_event", "daily_drawdown", "low_liquidity"]

    def test_default_manager_runs_four_rules(self, ohlcv: pd.DataFrame) -> None:
        assessment = RiskManager().assess(snap(ohlcv))
        assert len(assessment.checks) == 4  # back-compat: same set, same order
        json.dumps(assessment.as_dict())

    def test_constructor_params_flow_into_rules(self, ohlcv: pd.DataFrame) -> None:
        manager = RiskManager(max_daily_drawdown=0.01)
        assessment = manager.assess(snap(ohlcv), context={"daily_pnl_pct": -0.02})
        assert assessment.vetoed

    def test_custom_rule_list_is_composable(self, ohlcv: pd.DataFrame) -> None:
        """I7: extra rules plug in without touching the manager."""
        manager = RiskManager(rules=[*default_rules(), MaxPositionSize(0.25)])
        assessment = manager.assess(snap(ohlcv), context={"proposed_position_fraction": 0.9})
        assert assessment.vetoed
        assert len(assessment.checks) == 5

    def test_single_veto_still_blocks(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """I5: one veto among many passes is absolute."""

        class AlwaysVeto(RiskRule):
            name = "always_veto"

            def check(self, snapshot, report=None, context=None):  # type: ignore[override]
                return self.veto("synthetic veto")

        manager = RiskManager(rules=[*default_rules(), AlwaysVeto()])
        assessment = manager.assess(snap(uptrend_ohlcv))
        assert assessment.vetoed
        assert any("synthetic veto" in v for v in assessment.vetoes)

    def test_veto_blocks_committee_decision(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """A rule-library veto flows through the Chair exactly like an M1 veto (I5)."""
        from quantos.committee.analysts import default_analysts
        from quantos.committee.base import Direction
        from quantos.committee.committee import InvestmentCommittee

        committee = InvestmentCommittee(
            analysts=default_analysts(),
            risk_manager=RiskManager(rules=[MaxPositionSize(0.25)]),
        )
        snapshot = snap(
            uptrend_ohlcv,
            macro={"dxy_trend": -0.9, "rates_trend": -0.5, "risk_appetite": 0.9},
            sentiment={"score": 0.6},
            onchain={"net_exchange_flow": -1_500.0, "whale_accumulation": 0.8},
        )
        decision = committee.deliberate(snapshot, context={"proposed_position_fraction": 0.9})
        assert decision.blocked_by_risk
        assert decision.direction is Direction.FLAT
