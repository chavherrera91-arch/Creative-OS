"""WP-3.5 — position sizing: bounded by risk limits (I5), deterministic (I8)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from quantos.committee.base import Direction
from quantos.committee.decision import CommitteeDecision
from quantos.risk.limits import MaxPositionSize
from quantos.sizing.base import PositionSizer
from quantos.sizing.sizers import FractionalKellySizer, RiskParitySizer, VolTargetSizer


def make_decision(
    direction: Direction = Direction.LONG,
    approved: bool = True,
    confidence: float = 0.8,
    blocked_by_risk: bool = False,
) -> CommitteeDecision:
    return CommitteeDecision(
        symbol="BTC/USDT",
        timeframe="1h",
        price=100.0,
        direction=direction,
        approved=approved,
        confidence=confidence,
        blocked_by_risk=blocked_by_risk,
    )


ALL_SIZERS: list[Any] = [VolTargetSizer(), FractionalKellySizer(), RiskParitySizer()]


class TestProtocolAndHardRules:
    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_satisfies_protocol(self, sizer: PositionSizer) -> None:
        assert isinstance(sizer, PositionSizer)

    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_vetoed_decision_sizes_to_zero(self, sizer: PositionSizer) -> None:
        """I5: a sizer can never revive a vetoed decision."""
        vetoed = make_decision(approved=False, blocked_by_risk=True, confidence=0.99)
        assert sizer.size(vetoed, vol=0.5) == 0.0

    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_unapproved_decision_sizes_to_zero(self, sizer: PositionSizer) -> None:
        stood_down = make_decision(approved=False, direction=Direction.FLAT)
        assert sizer.size(stood_down, vol=0.5) == 0.0

    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_short_decisions_size_negative(self, sizer: PositionSizer) -> None:
        short = make_decision(direction=Direction.SHORT)
        assert sizer.size(short, vol=0.5) < 0.0

    @pytest.mark.parametrize(
        "sizer",
        [
            VolTargetSizer(target_vol=5.0, max_fraction=0.5, limit=MaxPositionSize(0.1)),
            FractionalKellySizer(kelly_fraction=1.0, max_fraction=0.5, limit=MaxPositionSize(0.1)),
            RiskParitySizer(risk_budget=5.0, max_fraction=0.5, limit=MaxPositionSize(0.1)),
        ],
        ids=lambda s: type(s).__name__,
    )
    def test_never_breaches_risk_limit(self, sizer: PositionSizer) -> None:
        """Acceptance: even an aggressive config cannot exceed MaxPositionSize (I5)."""
        greedy = make_decision(confidence=1.0)
        for vol in (None, 0.001, 0.01, 0.2, 5.0):
            assert abs(sizer.size(greedy, vol=vol)) <= 0.1 + 1e-12

    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_never_exceeds_own_cap(self, sizer: PositionSizer) -> None:
        greedy = make_decision(confidence=1.0)
        for vol in (None, 0.0001, 10.0):
            assert abs(sizer.size(greedy, vol=vol)) <= 0.25 + 1e-12

    @pytest.mark.parametrize("sizer", ALL_SIZERS, ids=lambda s: type(s).__name__)
    def test_deterministic(
        self, sizer: PositionSizer, assert_reproducible: Callable[..., Any]
    ) -> None:
        decision = make_decision(confidence=0.7)
        assert_reproducible(lambda: sizer.size(decision, vol=0.4, corr=0.3))


class TestVolTargetSizer:
    def test_size_falls_as_vol_rises(self) -> None:
        """Acceptance: vol-targeting reduces size when volatility rises."""
        sizer = VolTargetSizer(target_vol=0.2, max_fraction=1.0)
        decision = make_decision(confidence=0.8)
        calm = sizer.size(decision, vol=0.3)
        stormy = sizer.size(decision, vol=1.2)
        assert calm > stormy > 0.0
        assert stormy == pytest.approx(calm / 4.0)  # inverse in vol

    def test_low_vol_hits_the_cap(self) -> None:
        sizer = VolTargetSizer(target_vol=0.2, max_fraction=0.25)
        assert sizer.size(make_decision(confidence=1.0), vol=0.01) == pytest.approx(0.25)

    def test_no_vol_falls_back_to_confidence_scaled_cap(self) -> None:
        sizer = VolTargetSizer(max_fraction=0.25)
        assert sizer.size(make_decision(confidence=0.6)) == pytest.approx(0.25 * 0.6)

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError):
            VolTargetSizer(target_vol=0.0)
        with pytest.raises(ValueError):
            VolTargetSizer(max_fraction=0.0)


class TestFractionalKellySizer:
    def test_scales_with_confidence(self) -> None:
        sizer = FractionalKellySizer(kelly_fraction=0.5, max_fraction=1.0)
        low = sizer.size(make_decision(confidence=0.2))
        high = sizer.size(make_decision(confidence=0.6))
        assert high == pytest.approx(3.0 * low)
        assert high == pytest.approx(0.5 * 0.6)  # kelly_fraction * confidence

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError):
            FractionalKellySizer(kelly_fraction=0.0)
        with pytest.raises(ValueError):
            FractionalKellySizer(kelly_fraction=1.5)


class TestRiskParitySizer:
    def test_inverse_in_vol(self) -> None:
        sizer = RiskParitySizer(risk_budget=0.05, max_fraction=1.0)
        decision = make_decision()
        assert sizer.size(decision, vol=0.1) == pytest.approx(0.5)
        assert sizer.size(decision, vol=0.5) == pytest.approx(0.1)

    def test_correlation_discount(self) -> None:
        sizer = RiskParitySizer(risk_budget=0.05, max_fraction=1.0)
        decision = make_decision()
        uncorrelated = sizer.size(decision, vol=0.25, corr=0.0)
        crowded = sizer.size(decision, vol=0.25, corr={"ETH/USDT": 0.9, "SOL/USDT": 0.7})
        assert crowded < uncorrelated

    def test_negative_correlation_never_boosts(self) -> None:
        sizer = RiskParitySizer(risk_budget=0.05, max_fraction=1.0)
        decision = make_decision()
        hedged = sizer.size(decision, vol=0.25, corr=-0.8)
        assert hedged == pytest.approx(sizer.size(decision, vol=0.25, corr=0.0))


class TestExecutorConsultsSizer:
    def test_engine_uses_sizer_fraction(self) -> None:
        from quantos.config import Settings
        from quantos.execution.interfaces import PaperExecutionEngine
        from quantos.paper.broker import PaperBroker

        broker = PaperBroker(cash=100_000.0, fee_bps=0.0, slippage_bps=0.0)
        engine = PaperExecutionEngine(
            broker=broker,
            settings=Settings(max_position_fraction=0.25),
            sizer=VolTargetSizer(target_vol=0.2, max_fraction=0.25),
        )
        decision = make_decision(confidence=0.8)
        record = engine.execute(decision, vol=0.8)  # leverage 0.25 * conf 0.8 = 0.2
        assert record is not None
        assert record.notional == pytest.approx(100_000.0 * 0.2, rel=1e-6)

    def test_sizer_cannot_breach_settings_limit(self) -> None:
        """I5: the engine clamps whatever the sizer asks for."""
        from quantos.config import Settings
        from quantos.execution.interfaces import PaperExecutionEngine
        from quantos.paper.broker import PaperBroker

        class GreedySizer:
            def size(
                self,
                decision: CommitteeDecision,
                portfolio: dict[str, Any] | None = None,
                vol: float | None = None,
                corr: Any = None,
            ) -> float:
                return 5.0  # 500% of equity — must be clamped

        broker = PaperBroker(cash=100_000.0, fee_bps=0.0, slippage_bps=0.0)
        engine = PaperExecutionEngine(
            broker=broker, settings=Settings(max_position_fraction=0.25), sizer=GreedySizer()
        )
        record = engine.execute(make_decision(confidence=1.0), vol=0.5)
        assert record is not None
        assert record.notional <= 100_000.0 * 0.25 * (1.0 + 1e-9)

    def test_engine_without_sizer_unchanged(self) -> None:
        """Back-compat: the M1 rule still applies when no sizer is wired."""
        from quantos.config import Settings
        from quantos.execution.interfaces import PaperExecutionEngine
        from quantos.paper.broker import PaperBroker

        broker = PaperBroker(cash=100_000.0, fee_bps=0.0, slippage_bps=0.0)
        engine = PaperExecutionEngine(broker=broker, settings=Settings(max_position_fraction=0.25))
        record = engine.execute(make_decision(confidence=0.8))
        assert record is not None
        assert record.notional == pytest.approx(100_000.0 * 0.25 * 0.8, rel=1e-6)

    def test_vetoed_decision_never_reaches_broker(self) -> None:
        """I5 defence in depth: the gate blocks before the sizer is even asked."""
        from quantos.execution.interfaces import PaperExecutionEngine

        engine = PaperExecutionEngine(sizer=VolTargetSizer())
        vetoed = make_decision(approved=False, blocked_by_risk=True, confidence=0.99)
        assert engine.execute(vetoed, vol=0.2) is None

    def test_factory_still_refuses_live(self) -> None:
        """I1 guard intact after the sizing wiring."""
        from quantos.execution.interfaces import LiveExecutionDisabled, build_execution_engine

        with pytest.raises(LiveExecutionDisabled):
            build_execution_engine(live=True, sizer=VolTargetSizer())
