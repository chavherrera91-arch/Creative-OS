"""The Knowledge Engine (module 16) — turn events into an explainable graph.

News, on-chain and macro events become weighted relations in a
:class:`KnowledgeGraph`: ``ETF ──positive_news──▶ rally ──co_occurs──▶
bull_regime``. The default extractor is a deterministic lexicon +
co-occurrence baseline (no dependency, I6); an LLM triple-extractor can be
injected behind the ``[llm]`` extra without changing the port (I7).

The engine only *reads* and *relates* recorded evidence — every edge carries
the event ids that produced it (I4), and the same events always build the same
graph and surface the same inferences (I8). It feeds the committee forward:
:meth:`related` and :meth:`paths` hand it explainable context, never orders.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from quantos.knowledge.graph import Edge, KnowledgeGraph

__all__ = ["KnowledgeEngine", "TripleExtractor", "llm_triple_extractor"]

#: An extractor maps free text to ``(src, relation, dst)`` triples.
TripleExtractor = Callable[[str], list[tuple[str, str, str]]]

_TOKEN = re.compile(r"[a-z0-9]+")

#: Minimal built-in lexicon: canonical entity -> the keywords that name it.
DEFAULT_LEXICON: dict[str, tuple[str, ...]] = {
    "ETF": ("etf", "etfs"),
    "BlackRock": ("blackrock",),
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum"),
    "rally": ("rally", "rallies", "surge", "surges"),
    "selloff": ("selloff", "crash", "plunge", "plunges"),
    "inflows": ("inflow", "inflows"),
    "outflows": ("outflow", "outflows"),
    "CPI": ("cpi", "inflation"),
    "rate_hike": ("hike", "hikes", "tightening"),
    "bull_regime": ("bull", "bullish"),
    "bear_regime": ("bear", "bearish"),
}


def _sentiment_relation(sentiment: float | None) -> str:
    """Map an event's sentiment to a relation label."""
    if sentiment is None:
        return "co_occurs"
    if sentiment > 0.15:
        return "positive_news"
    if sentiment < -0.15:
        return "negative_news"
    return "co_occurs"


class KnowledgeEngine:
    """Build and query a relationship graph from platform events."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        lexicon: Mapping[str, tuple[str, ...]] | None = None,
        extractor: TripleExtractor | None = None,
    ) -> None:
        """
        Args:
            graph: the graph to grow (a fresh one when omitted).
            lexicon: canonical-entity -> keyword map for the baseline
                extractor; :data:`DEFAULT_LEXICON` when omitted.
            extractor: optional ``text -> triples`` backend (e.g. LLM-driven);
                the deterministic lexicon co-occurrence baseline when omitted.
        """
        self.graph = graph if graph is not None else KnowledgeGraph()
        self.lexicon = dict(lexicon or DEFAULT_LEXICON)
        self._extractor = extractor
        self._keyword_index = {
            keyword: entity for entity, keywords in self.lexicon.items() for keyword in keywords
        }

    # -- ingestion ------------------------------------------------------------
    def ingest(self, event: Mapping[str, Any]) -> list[Edge]:
        """Extract and add the relations in one event; returns new/updated edges.

        An event is ``{"id", "text", "sentiment"?, "weight"?, "relation"?}``.
        Explicit ``(src, relation, dst)`` triples may be supplied directly via
        an ``edges`` list; otherwise the extractor reads ``text``.
        """
        event_id = str(event.get("id", ""))
        weight = float(event.get("weight", 1.0))
        provenance = (event_id,) if event_id else ()
        touched: list[Edge] = []

        for src, relation, dst in event.get("edges", []):
            touched.append(self.graph.add(src, relation, dst, weight, provenance))

        text = str(event.get("text", ""))
        if text:
            if self._extractor is not None:
                triples = self._extractor(text)
            else:
                relation = str(event.get("relation") or _sentiment_relation(event.get("sentiment")))
                triples = self._lexicon_triples(text, relation)
            for src, rel, dst in triples:
                touched.append(self.graph.add(src, rel, dst, weight, provenance))
        return touched

    def ingest_many(self, events: Iterable[Mapping[str, Any]]) -> KnowledgeGraph:
        """Ingest a batch of events; returns the grown graph."""
        for event in events:
            self.ingest(event)
        return self.graph

    def _lexicon_triples(self, text: str, relation: str) -> list[tuple[str, str, str]]:
        """Chain the recognised entities in appearance order with ``relation``."""
        seen: list[str] = []
        for token in _TOKEN.findall(text.lower()):
            entity = self._keyword_index.get(token)
            if entity is not None and (not seen or seen[-1] != entity):
                seen.append(entity)
        return [(seen[i], relation, seen[i + 1]) for i in range(len(seen) - 1)]

    # -- queries --------------------------------------------------------------
    def related(self, entity: str, k: int = 5) -> list[Edge]:
        """The ``k`` strongest direct relations from ``entity`` (committee context)."""
        return self.graph.out_edges(entity)[:k]

    def paths(self, src: str, dst: str, max_depth: int = 4) -> list[list[Edge]]:
        """Explainable chains from ``src`` to ``dst`` (strongest first)."""
        return self.graph.paths(src, dst, max_depth=max_depth)

    def explain(self, src: str, dst: str, max_depth: int = 4) -> str:
        """The strongest ``src ▸ … ▸ dst`` chain as a human-readable line."""
        chains = self.paths(src, dst, max_depth=max_depth)
        if not chains:
            return f"no known chain from {src!r} to {dst!r}"
        chain = chains[0]
        steps = " ▸ ".join(f"{e.src} ──{e.relation}──▶ {e.dst}" for e in chain)
        return f"{steps}  (weight {sum(e.weight for e in chain):.1f})"

    def infer(self, entity: str, max_depth: int = 4) -> list[dict[str, Any]]:
        """Surface *implicit* relations: entities reachable but not directly linked.

        Returns one record per implied target with the connecting path's weight
        (minimum edge weight along the chain) and the intermediary — the
        "you don't see it stated, but the record implies it" layer (I4/I8).
        """
        direct = set(self.graph.neighbors(entity))
        implied: dict[str, dict[str, Any]] = {}
        for target in self.graph.entities:
            if target == entity or target in direct:
                continue
            chains = self.graph.paths(entity, target, max_depth=max_depth)
            if not chains:
                continue
            chain = chains[0]
            strength = min(e.weight for e in chain)
            implied[target] = {
                "entity": target,
                "via": [e.dst for e in chain[:-1]],
                "weight": strength,
                "relations": [e.relation for e in chain],
            }
        return sorted(implied.values(), key=lambda r: (-r["weight"], r["entity"]))


def llm_triple_extractor(client: Any) -> TripleExtractor:
    """Wrap an :class:`~quantos.llm.client.LLMClient` as a triple extractor.

    Asks the model for ``[[src, relation, dst], …]`` JSON and parses it; any
    backend/parse failure yields no triples, so the engine degrades to
    silence rather than fabricating relations (I3). Optional, ``[llm]``-gated.
    """
    import json

    schema = {"triples": [["src", "relation", "dst"]]}

    def extract(text: str) -> list[tuple[str, str, str]]:
        prompt = (
            "Extract factual (subject, relation, object) triples from this "
            f"financial text as JSON {{'triples': [[src, relation, dst], ...]}}:\n{text}"
        )
        try:
            raw = client.complete(prompt, schema=schema)
            payload = json.loads(raw)
            triples = payload["triples"] if isinstance(payload, dict) else payload
            return [
                (str(t[0]), str(t[1]), str(t[2]))
                for t in triples
                if isinstance(t, (list, tuple)) and len(t) == 3
            ]
        except Exception:  # noqa: BLE001 - extraction is best-effort (I3)
            return []

    return extract
