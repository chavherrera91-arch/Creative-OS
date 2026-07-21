"""WP-7.3 — Meta-Learning Engine: regime-validated family selection (I4/I8)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from quantos.memory import DecisionArchive
from quantos.meta import (
    BaselineMetaLearner,
    MetaLearner,
    RegimePerformanceTable,
)
from quantos.strategy.generator import generate
from quantos.strategy.lab import LabRecord, LabResult
from tests.test_archive import fake_record


@dataclass(frozen=True)
class StubSpec:
    family: str
    key: str = "stub@1"


@dataclass(frozen=True)
class StubStrategy:
    spec: StubSpec


def seeded_learner() -> BaselineMetaLearner:
    """Family A validated in TREND_UP, family B validated in RANGE."""
    table = RegimePerformanceTable()
    for score in (1.0, 2.0, 1.5):
        table.record("A", "TREND_UP", score)
        table.record("B", "RANGE", score)
    # B has evidence in TREND_UP too, but it is losing evidence.
    for score in (-1.0, -2.0, -0.5):
        table.record("B", "TREND_UP", score)
    return BaselineMetaLearner(table)


class TestTable:
    def test_stats_and_validation_bar(self) -> None:
        learner = seeded_learner()
        stats = learner.table.stats("A", "TREND_UP")
        assert stats.n_samples == 3 and stats.win_rate == 1.0
        assert learner.table.validated("TREND_UP") == ["A"]
        assert learner.table.validated("RANGE") == ["B"]
        assert learner.table.validated("CRISIS") == []

    def test_unknown_regime_rejected(self) -> None:
        with pytest.raises(ValueError):
            RegimePerformanceTable().record("A", "SIDEWAYS", 1.0)

    def test_serialises(self) -> None:
        import json

        json.dumps(seeded_learner().table.as_dict())


class TestSelection:
    universe = [StubStrategy(StubSpec("A")), StubStrategy(StubSpec("B"))]

    def test_protocol(self) -> None:
        assert isinstance(BaselineMetaLearner(), MetaLearner)

    def test_selects_only_regime_validated_family(self) -> None:
        selection = seeded_learner().select("TREND_UP", self.universe)
        assert [s.spec.family for s in selection.selected] == ["A"]
        assert not selection.stand_down
        # explainable verdicts for both families (I4)
        assert "validated for TREND_UP" in selection.report["A"]
        assert "rejected for TREND_UP" in selection.report["B"]

    def test_range_flips_the_selection(self) -> None:
        selection = seeded_learner().select("RANGE", self.universe)
        assert [s.spec.family for s in selection.selected] == ["B"]

    def test_unvalidated_regime_stands_down(self) -> None:
        selection = seeded_learner().select("CRISIS", self.universe)
        assert selection.stand_down and selection.selected == []
        assert all("rejected" in verdict for verdict in selection.report.values())

    def test_selection_serialises(self) -> None:
        payload = seeded_learner().select("TREND_UP", self.universe).as_dict()
        assert payload["regime"] == "TREND_UP" and payload["stand_down"] is False


class TestLearning:
    def closed_archive(self, family: str, pnls: list[float]) -> DecisionArchive:
        archive = DecisionArchive()
        for i, pnl in enumerate(pnls):
            record = fake_record(as_of=f"2024-01-{10 + i:02d}T00:00:00+00:00", regime="TREND_UP")
            record["strategies_considered"] = [{"family": family, "name": f"s{i}"}]
            did = archive.record(record)
            archive.record_outcome(did, pnl=pnl)
        return archive

    def test_update_moves_family_into_validation(self) -> None:
        learner = BaselineMetaLearner()
        assert learner.select("TREND_UP", [StubStrategy(StubSpec("C"))]).stand_down
        learner.update(self.closed_archive("C", [3.0, 2.0, 4.0]))
        selection = learner.select("TREND_UP", [StubStrategy(StubSpec("C"))])
        assert [s.spec.family for s in selection.selected] == ["C"]

    def test_update_moves_family_out_as_outcomes_sour(self) -> None:
        learner = BaselineMetaLearner()
        learner.update(self.closed_archive("C", [3.0, 2.0, 4.0]))
        assert not learner.select("TREND_UP", [StubStrategy(StubSpec("C"))]).stand_down
        learner.update(self.closed_archive("C", [-9.0, -9.0, -9.0, -9.0]))
        assert learner.select("TREND_UP", [StubStrategy(StubSpec("C"))]).stand_down

    def test_update_is_idempotent(self) -> None:
        learner = BaselineMetaLearner()
        archive = self.closed_archive("C", [3.0, 2.0, 4.0])
        learner.update(archive)
        learner.update(archive)  # same outcomes again — must not double-count
        assert learner.table.stats("C", "TREND_UP").n_samples == 3

    def test_ingest_lab_records_survivors_only(self) -> None:
        specs = generate(2, seed=11)
        records = [
            LabRecord(rank=1, spec=specs[0], fitness=2.0, survived=True, tested_regime="TREND_UP"),
            LabRecord(
                rank=2, spec=specs[1], fitness=-3.0, survived=False, tested_regime="TREND_UP"
            ),
        ]
        learner = BaselineMetaLearner()
        added = learner.ingest_lab(
            LabResult(run_id="run", records=records, tested_regime="TREND_UP")
        )
        assert added == 1
        assert learner.table.stats(specs[0].family, "TREND_UP").n_samples == 1
        assert learner.table.stats(specs[1].family, "TREND_UP").n_samples == 0
