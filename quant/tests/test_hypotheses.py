"""WP-9.5 — Hypothesis Generator: rank questions, register as experiments (I8)."""

from __future__ import annotations

from quantos.knowledge import KnowledgeEngine
from quantos.learning import SelfEvaluator
from quantos.research import ExperimentRegistry, HypothesisGenerator
from quantos.research.hypotheses import Hypothesis

# Reuse the WP-9.4 decaying-archive builder.
from tests.test_self_eval import decaying_archive


def seeded_knowledge() -> KnowledgeEngine:
    engine = KnowledgeEngine()
    engine.ingest_many(
        [
            {"id": "e1", "text": "BlackRock ETF sees record inflows", "sentiment": 0.8},
            {"id": "e2", "text": "ETF inflows fuel a BTC rally", "sentiment": 0.7},
        ]
    )
    return engine


class TestGeneration:
    def test_ranks_hypotheses_from_self_eval(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        hypotheses = HypothesisGenerator().generate(self_eval=report)
        questions = " ".join(h.question for h in hypotheses)
        assert "rsi" in questions  # decayed signal became a question
        # Ranked descending by priority.
        priorities = [h.priority for h in hypotheses]
        assert priorities == sorted(priorities, reverse=True)

    def test_dying_family_from_archive(self) -> None:
        from quantos.memory import DecisionArchive

        archive = DecisionArchive()
        for i in range(4):
            did = archive.record(
                {
                    "symbol": "BTC/USDT",
                    "timeframe": "1h",
                    "price": 100.0,
                    "direction": "LONG",
                    "approved": True,
                    "confidence": 0.6,
                    "blocked_by_risk": False,
                    "reasons": [f"f{i}"],
                    "opinions": [],
                    "regime": {"label": "TREND_UP"},
                    "strategies_considered": [{"name": "b", "family": "breakout"}],
                    "run_manifest": {"seed": 1},
                    "as_of": "2024-02-01T00:00:00+00:00",
                }
            )
            archive.record_outcome(did, pnl=-20.0)
        hypotheses = HypothesisGenerator().generate(archive=archive)
        assert any("breakout" in h.question and "dying" in h.question for h in hypotheses)

    def test_new_variable_from_knowledge(self) -> None:
        hypotheses = HypothesisGenerator().generate(knowledge=seeded_knowledge())
        assert any("new-variable" in h.tags for h in hypotheses)

    def test_is_deterministic(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        a = HypothesisGenerator().generate(self_eval=report, knowledge=seeded_knowledge())
        b = HypothesisGenerator().generate(self_eval=report, knowledge=seeded_knowledge())
        assert [h.as_dict() for h in a] == [h.as_dict() for h in b]


class TestRegistration:
    def test_hypotheses_become_queryable_experiments(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        generator = HypothesisGenerator()
        hypotheses = generator.generate(self_eval=report, knowledge=seeded_knowledge())
        registry = ExperimentRegistry()
        ids = generator.register(registry, hypotheses)
        assert ids
        registered = registry.query(tag="hypothesis")
        assert len(registered) == len(hypotheses)
        assert all(e.status == "open" for e in registered)

    def test_registration_is_idempotent(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        generator = HypothesisGenerator()
        hypotheses = generator.generate(self_eval=report)
        registry = ExperimentRegistry()
        first = set(generator.register(registry, hypotheses))
        second = set(generator.register(registry, hypotheses))
        assert first == second  # same content → same ids (I8)
        assert len(registry) == len(first)


class TestLLMIdeation:
    def test_llm_hypotheses_are_added_when_available(self) -> None:
        class Fake:
            def complete(self, prompt: str, schema: dict | None = None) -> str:
                return (
                    '{"hypotheses": [{"question": "Does funding rate lead price?", '
                    '"rationale": "x"}]}'
                )

        hypotheses = HypothesisGenerator(client=Fake()).generate()
        assert any("funding rate" in h.question for h in hypotheses)

    def test_llm_failure_is_silent(self) -> None:
        class Exploding:
            def complete(self, prompt: str, schema: dict | None = None) -> str:
                raise RuntimeError("down")

        # No other source → no hypotheses, and no crash (I3/I6).
        assert HypothesisGenerator(client=Exploding()).generate() == []

    def test_generate_returns_hypothesis_objects(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        hypotheses = HypothesisGenerator().generate(self_eval=report)
        assert hypotheses and all(isinstance(h, Hypothesis) for h in hypotheses)
