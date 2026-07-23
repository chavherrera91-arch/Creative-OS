"""WP-9.1 — Knowledge Engine: build explainable edges, infer, path (I8)."""

from __future__ import annotations

from quantos.knowledge import KnowledgeEngine, KnowledgeGraph, llm_triple_extractor
from quantos.llm.client import MockLLMClient


def seeded_events() -> list[dict]:
    return [
        {"id": "e1", "text": "BlackRock ETF sees record inflows", "sentiment": 0.8},
        {"id": "e2", "text": "ETF inflows fuel a BTC rally", "sentiment": 0.7},
        {"id": "e3", "text": "The rally pushes the market into a bull regime", "sentiment": 0.6},
    ]


class TestGraph:
    def test_edges_reinforce_and_carry_provenance(self) -> None:
        graph = KnowledgeGraph()
        graph.add("ETF", "positive_news", "rally", weight=1.0, provenance=("e1",))
        edge = graph.add("ETF", "positive_news", "rally", weight=0.5, provenance=("e2",))
        assert edge.weight == 1.5  # reinforced
        assert edge.provenance == ("e1", "e2")  # merged, sorted (I4)
        assert len(graph) == 1

    def test_paths_are_ranked_by_weight(self) -> None:
        graph = KnowledgeGraph()
        graph.add("A", "r", "B", weight=1.0)
        graph.add("B", "r", "D", weight=1.0)
        graph.add("A", "r", "C", weight=5.0)
        graph.add("C", "r", "D", weight=5.0)
        chains = graph.paths("A", "D")
        assert [e.dst for e in chains[0]] == ["C", "D"]  # strongest chain first

    def test_paths_have_no_cycles(self) -> None:
        graph = KnowledgeGraph()
        graph.add("A", "r", "B")
        graph.add("B", "r", "A")
        assert graph.paths("A", "A") == []  # no self-return via a cycle


class TestEngine:
    def test_builds_expected_chain_from_events(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest_many(seeded_events())
        chains = engine.paths("ETF", "rally")
        assert chains, "expected an ETF ▸ rally chain"
        assert chains[0][0].src == "ETF"
        assert chains[0][-1].dst == "rally"

    def test_full_chain_to_bull_regime(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest_many(seeded_events())
        chains = engine.paths("ETF", "bull_regime")
        assert chains
        entities = [chains[0][0].src] + [e.dst for e in chains[0]]
        assert "rally" in entities and entities[-1] == "bull_regime"

    def test_is_deterministic(self) -> None:
        a, b = KnowledgeEngine(), KnowledgeEngine()
        a.ingest_many(seeded_events())
        b.ingest_many(list(reversed(seeded_events())))
        assert a.graph.as_dict() == b.graph.as_dict()  # order-independent (I8)

    def test_infer_surfaces_implicit_relations(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest_many(seeded_events())
        implied = {r["entity"] for r in engine.infer("ETF")}
        assert "bull_regime" in implied  # not directly linked, but implied

    def test_explain_is_human_readable(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest_many(seeded_events())
        line = engine.explain("ETF", "rally")
        assert "ETF" in line and "rally" in line and "▶" in line

    def test_explicit_edges_are_accepted(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest({"id": "x", "edges": [("gold", "hedges", "inflation")]})
        assert engine.graph.neighbors("gold") == ["inflation"]

    def test_negative_sentiment_labels_the_relation(self) -> None:
        engine = KnowledgeEngine()
        engine.ingest(
            {"id": "n1", "text": "CPI shock triggers a market selloff", "sentiment": -0.8}
        )
        relations = {e.relation for e in engine.graph.edges}
        assert relations == {"negative_news"}


class TestLLMExtractor:
    def test_mock_llm_extractor_degrades_gracefully(self) -> None:
        # The mock returns a generic JSON echo, not triples — the extractor
        # must never crash and simply contributes nothing (I3/I6).
        extract = llm_triple_extractor(MockLLMClient(seed=1))
        assert extract("BlackRock buys BTC") == []

    def test_extractor_parses_well_formed_triples(self) -> None:
        class Fake:
            def complete(self, prompt: str, schema: dict | None = None) -> str:
                return '{"triples": [["BlackRock", "buys", "BTC"]]}'

        engine = KnowledgeEngine(extractor=llm_triple_extractor(Fake()))
        engine.ingest({"id": "e", "text": "irrelevant, the extractor decides"})
        assert engine.graph.neighbors("BlackRock") == ["BTC"]
