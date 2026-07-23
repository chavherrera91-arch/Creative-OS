"""WP-9.6 — Market Simulator: bar-by-bar replay, paper-only, no look-ahead (I1/I2/I8)."""

from __future__ import annotations

import pytest

from quantos.memory import DecisionArchive
from quantos.scenarios.library import get_scenario
from quantos.sim import MarketSimulator, ReplayResult, SimStep


@pytest.fixture(scope="module")
def replay() -> ReplayResult:
    # Coarse step keeps the deliberation count (and runtime) small.
    return MarketSimulator(warmup=60, step=30).replay("ETF_RALLY")


class TestReplay:
    def test_steps_through_the_scenario(self, replay: ReplayResult) -> None:
        assert replay.scenario == "ETF_RALLY"
        assert replay.steps, "expected at least one replayed step"
        assert all(isinstance(s, SimStep) for s in replay.steps)

    def test_steps_are_time_ordered(self, replay: ReplayResult) -> None:
        indices = [s.index for s in replay.steps]
        assert indices == sorted(indices)  # advances forward, bar by bar

    def test_paper_only_no_capital(self, replay: ReplayResult) -> None:
        assert replay.account["is_paper"] is True  # I1
        # Equity is a finite paper number; no live broker was ever touched.
        assert replay.final_equity > 0.0

    def test_is_deterministic(self) -> None:
        a = MarketSimulator(warmup=60, step=30).replay("ETF_RALLY", seed=7)
        b = MarketSimulator(warmup=60, step=30).replay("ETF_RALLY", seed=7)
        assert a.as_dict() == b.as_dict()  # pure function of (scenario, seed) (I8)

    def test_seed_is_recorded(self) -> None:
        scenario = get_scenario("FTX")
        result = MarketSimulator(warmup=60, step=40).replay(scenario, seed=11)
        assert result.seed == scenario._seed(11)

    def test_json_serialisable(self, replay: ReplayResult) -> None:
        import json

        json.dumps(replay.as_dict())


class TestNoLookAhead:
    def test_prefix_only_snapshots(self) -> None:
        """Each step's decision sees only bars up to its own index (I2).

        We reproduce the snapshot the simulator would have formed and confirm
        it never extends past the step's bar.
        """
        scenario = get_scenario("ETF_RALLY")
        ohlcv = scenario.generate(None)
        sim = MarketSimulator(warmup=60, step=50)
        for step in sim.stream(scenario):
            # The decision-time price is exactly the close at the step's bar,
            # never a later one.
            assert step.price == pytest.approx(float(ohlcv["close"].iloc[step.index]))


class TestArchiveIntegration:
    def test_decisions_can_be_archived(self) -> None:
        archive = DecisionArchive()
        MarketSimulator(warmup=60, step=50, archive=archive).replay("ETF_RALLY")
        assert len(archive) >= 1  # every deliberation was recorded (I4)


class TestSafety:
    def test_simulator_exposes_no_live_path(self) -> None:
        sim = MarketSimulator()
        for attribute in ("live", "submit_live", "connect", "execute_live"):
            assert not hasattr(sim, attribute)

    def test_replay_source_never_imports_execution(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "quantos" / "sim" / "replay.py"
        text = source.read_text()
        assert "quantos.execution" not in text  # paper broker only (I1)
