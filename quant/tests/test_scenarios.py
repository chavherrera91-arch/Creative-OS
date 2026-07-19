"""WP-4.5 — scenario library + simulator: shapes, regime recovery, paper only (I1/I8)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quantos.backtest.engine import BacktestResult
from quantos.committee.committee import regime_aware_committee
from quantos.features import indicators as ind
from quantos.regime.classifier import RuleRegimeClassifier
from quantos.scenarios.library import SCENARIOS, Phase, Scenario, get_scenario, scenario_names
from quantos.scenarios.simulator import simulate

EXPECTED_NAMES = {"COVID_CRASH", "FTX", "ETF_RALLY", "BEAR_2022", "BULL_2021"}


def drawdown(close: pd.Series) -> float:
    return float((close / close.cummax() - 1.0).min())


class TestLibrary:
    def test_the_named_scenarios_exist(self) -> None:
        assert set(scenario_names()) == EXPECTED_NAMES

    def test_unknown_scenario_raises_with_the_menu(self) -> None:
        with pytest.raises(KeyError, match="COVID_CRASH"):
            get_scenario("DOTCOM")

    def test_scenarios_validate_their_labels_and_core(self) -> None:
        with pytest.raises(ValueError, match="unknown regime label"):
            Scenario("X", "d", "MOON", (Phase(10, 0.0, 0.01),), 0)
        with pytest.raises(ValueError, match="out of range"):
            Scenario("X", "d", "RANGE", (Phase(10, 0.0, 0.01),), 3)

    def test_scenarios_serialise(self) -> None:
        for scenario in SCENARIOS.values():
            record = scenario.as_dict()
            json.dumps(record)
            assert record["regime_label"] == scenario.regime_label


class TestPathsAreDeterministicAndShaped:
    @pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
    def test_generation_is_reproducible(
        self, name: str, assert_reproducible: Callable[..., Any]
    ) -> None:
        """I8: same scenario + seed, same candles."""
        scenario = get_scenario(name)
        frame = assert_reproducible(scenario.generate)
        assert len(frame) == scenario.bars
        assert (frame["high"] >= frame[["open", "close"]].max(axis=1) - 1e-9).all()
        assert (frame["low"] <= frame[["open", "close"]].min(axis=1) + 1e-9).all()

    def test_a_different_seed_is_a_different_path(self) -> None:
        scenario = get_scenario("COVID_CRASH")
        assert not scenario.generate(seed=1)["close"].equals(scenario.generate(seed=2)["close"])

    def test_covid_crash_has_a_deep_drawdown(self) -> None:
        close = get_scenario("COVID_CRASH").generate()["close"]
        assert drawdown(close) < -0.30

    def test_ftx_collapses_and_stays_down(self) -> None:
        close = get_scenario("FTX").generate()["close"]
        assert drawdown(close) < -0.40
        assert close.iloc[-1] < close.iloc[0]

    def test_bull_and_etf_rally_trend_up(self) -> None:
        for name in ("BULL_2021", "ETF_RALLY"):
            close = get_scenario(name).generate()["close"]
            assert close.iloc[-1] / close.iloc[0] > 1.5, name

    def test_bear_2022_grinds_down(self) -> None:
        close = get_scenario("BEAR_2022").generate()["close"]
        assert close.iloc[-1] / close.iloc[0] < 0.6

    def test_stress_phases_carry_more_volume(self) -> None:
        scenario = get_scenario("COVID_CRASH")
        frame = scenario.generate()
        calm = frame["volume"].iloc[: scenario.phases[0].bars].mean()
        crash = frame["volume"].iloc[scenario.phases[0].bars : scenario.core_end].mean()
        assert crash > calm


class TestRegimeRecovery:
    """Acceptance: the Regime Engine recovers each scenario's labelled regime."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
    def test_classifier_recovers_the_ground_truth_on_the_core(self, name: str) -> None:
        scenario = get_scenario(name)
        state = RuleRegimeClassifier().classify(scenario.core_snapshot())
        assert state.label == scenario.regime_label, (
            f"{name}: expected {scenario.regime_label}, classified {state.label} "
            f"(probabilities {state.probabilities})"
        )
        assert state.evidence  # the recovery is explainable (I4)

    def test_core_snapshot_only_reveals_bars_up_to_the_core(self) -> None:
        """I2: the scored view ends at the core phase's last bar."""
        scenario = get_scenario("COVID_CRASH")
        snapshot = scenario.core_snapshot()
        assert snapshot.bars == scenario.core_end < scenario.bars
        full = scenario.generate()
        pd.testing.assert_frame_equal(snapshot.ohlcv, full.iloc[: scenario.core_end])


class TestSimulate:
    def test_a_callable_strategy_yields_a_backtest_result(self) -> None:
        def momentum(ohlcv: pd.DataFrame) -> pd.Series:
            fast = ind.ema(ohlcv["close"], 12)
            slow = ind.ema(ohlcv["close"], 48)
            return np.sign(fast - slow).fillna(0.0)

        result = simulate(momentum, "BULL_2021")
        assert isinstance(result, BacktestResult)
        assert np.isfinite(result.metrics["sharpe"])
        assert result.baselines  # edge is never claimed without baselines
        assert result.n_trades > 0

    def test_a_signal_strategy_object_works(self) -> None:
        class BuyAndHold:
            def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
                return pd.Series(1.0, index=ohlcv.index)

        result = simulate(BuyAndHold(), get_scenario("BEAR_2022"))
        assert result.equity.iloc[-1] < 1.0  # long-only loses the bear

    def test_an_unsupported_subject_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="cannot simulate"):
            simulate(object(), "FTX")

    def test_simulation_is_reproducible(self, assert_reproducible: Callable[..., Any]) -> None:
        """I8: same subject + scenario + seed, same result."""

        def flat_then_long(ohlcv: pd.DataFrame) -> pd.Series:
            positions = pd.Series(0.0, index=ohlcv.index)
            positions.iloc[len(ohlcv) // 2 :] = 1.0
            return positions

        assert_reproducible(lambda: simulate(flat_then_long, "ETF_RALLY").as_dict())

    def test_the_committee_can_be_simulated_offline(self) -> None:
        """The full M4 committee runs through a scenario — paper maths only (I1)."""
        committee = regime_aware_committee()
        result = simulate(committee, "ETF_RALLY", warmup=100, step=25)
        assert isinstance(result, BacktestResult)
        assert result.positions.abs().max() <= 1.0
        assert np.isfinite(result.metrics["total_return"])

    def test_no_capital_is_ever_touched(self) -> None:
        """I1: the simulator is pure research maths — no broker in the loop."""
        from pathlib import Path

        import quantos.scenarios.simulator as sim

        source = Path(sim.__file__).read_text()
        assert "PaperBroker" not in source
        assert "submit" not in source
        result = simulate(lambda ohlcv: pd.Series(0.0, index=ohlcv.index), "FTX")
        assert float(result.equity.iloc[-1]) == pytest.approx(1.0)  # flat = no P&L
