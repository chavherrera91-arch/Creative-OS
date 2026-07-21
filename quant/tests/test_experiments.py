"""WP-7.7 — Experiment Registry: hypothesis → result → conclusion, immutable."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantos.data.store import DuckDBStore
from quantos.research import ExperimentRegistry


class TestLedger:
    def test_round_trip(self) -> None:
        registry = ExperimentRegistry()
        eid = registry.register(
            "does the trend family survive HIGH_VOL?",
            setup={"seed": 42, "families": ["trend"], "regime": "HIGH_VOL"},
            tags=("strategy-lab", "regime"),
        )
        registry.complete(eid, result={"mean_fitness": -1.2}, conclusion="no — revoke it")
        experiment = registry.get(eid)
        assert experiment.completed
        assert experiment.setup["seed"] == 42  # replayable setup pinned (I8)
        assert experiment.conclusion == "no — revoke it"

    def test_registration_is_idempotent(self) -> None:
        registry = ExperimentRegistry()
        first = registry.register("h", setup={"seed": 1})
        second = registry.register("h", setup={"seed": 1})
        assert first == second and len(registry) == 1
        assert registry.register("h", setup={"seed": 2}) != first  # new setup, new id

    def test_completed_experiments_are_immutable(self) -> None:
        registry = ExperimentRegistry()
        eid = registry.register("h", setup={"seed": 1})
        registry.complete(eid, result={"x": 1}, conclusion="done")
        with pytest.raises(ValueError):
            registry.complete(eid, result={"x": 2}, conclusion="rewritten")
        assert registry.get(eid).result == {"x": 1}
        # re-registering the identical experiment cannot reopen it
        assert registry.register("h", setup={"seed": 1}) == eid
        assert registry.get(eid).completed

    def test_validation_and_unknown_ids(self) -> None:
        registry = ExperimentRegistry()
        with pytest.raises(ValueError):
            registry.register("   ")
        with pytest.raises(KeyError):
            registry.get("nope")
        with pytest.raises(KeyError):
            registry.complete("nope", result={}, conclusion="")


class TestQueries:
    def build(self) -> ExperimentRegistry:
        registry = ExperimentRegistry()
        self.a = registry.register("trend family in HIGH_VOL", tags=("strategy-lab",))
        self.b = registry.register("macro analyst weight too high?", tags=("audit",))
        registry.complete(self.b, result={"hit_rate": 0.3}, conclusion="lower it")
        return registry

    def test_by_status_tag_and_text(self) -> None:
        registry = self.build()
        assert [e.experiment_id for e in registry.query(status="open")] == [self.a]
        assert [e.experiment_id for e in registry.query(tag="audit")] == [self.b]
        assert [e.experiment_id for e in registry.query(text="macro")] == [self.b]

    def test_survives_restart_on_disk(self, tmp_path: Path) -> None:
        root = tmp_path / "lake"
        eid = ExperimentRegistry(DuckDBStore(root=root)).register("persists?", setup={"s": 1})
        reopened = ExperimentRegistry(DuckDBStore(root=root))
        assert reopened.get(eid).hypothesis == "persists?"
