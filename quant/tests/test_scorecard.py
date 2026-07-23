"""Strategy Score — one honest report card across the full validation battery."""

from __future__ import annotations

from quantos.backtest.scorecard import Scorecard, evaluate
from quantos.scenarios.library import get_scenario
from quantos.strategy.base import IndicatorStrategy
from quantos.strategy.generator import RandomStrategyGenerator


def a_strategy() -> tuple[IndicatorStrategy, object]:
    ohlcv = get_scenario("ETF_RALLY").generate(7)
    specs = RandomStrategyGenerator().generate(12, seed=7, diversity=0.4)
    strat = max(
        (IndicatorStrategy(s) for s in specs),
        key=lambda st: float(st.signals(ohlcv).diff().abs().sum()),
    )
    return strat, ohlcv


class TestScorecard:
    def test_produces_a_scored_verdict(self) -> None:
        strat, ohlcv = a_strategy()
        card = evaluate(strat, ohlcv, n_trials=12)
        assert isinstance(card, Scorecard)
        assert 0 <= card.score <= 100
        assert card.verdict in {
            "REJECTED",
            "NEEDS WORK",
            "PROMETEDORA — necesita más pruebas",
            "READY FOR PAPER TRADING",
        }

    def test_card_covers_the_full_battery(self) -> None:
        strat, ohlcv = a_strategy()
        names = {c.name for c in evaluate(strat, ohlcv).checks}
        # More than one lucky number: costs, out-of-sample, Monte Carlo, regimes, sensitivity.
        for expected in (
            "Profit Factor",
            "Sharpe",
            "Max Drawdown",
            "Out-of-Sample (DSR)",
            "Monte Carlo (peor DD)",
            "Robustez por régimen",
            "Sensibilidad",
            "Operaciones",
        ):
            assert expected in names

    def test_is_deterministic_and_serialisable(self) -> None:
        import json

        strat, ohlcv = a_strategy()
        first = evaluate(strat, ohlcv, n_trials=12).as_dict()
        second = evaluate(strat, ohlcv, n_trials=12).as_dict()
        assert first == second  # pure function of (strategy, data, seed) (I8)
        json.dumps(first)

    def test_score_reflects_passed_weight(self) -> None:
        strat, ohlcv = a_strategy()
        card = evaluate(strat, ohlcv, n_trials=12)
        total = sum(c.weight for c in card.checks)
        earned = sum(c.weight for c in card.checks if c.passed)
        assert card.score == round(100 * earned / total)
