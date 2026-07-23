"""The knowledge graph — a weighted, provenance-carrying relation store.

Entities (``ETF``, ``BlackRock``, ``rally``, ``bull_regime``, …) are nodes;
every edge is a *directed* ``src ──relation──▶ dst`` with an accumulated
weight and the provenance (event ids) that produced it. Re-observing the same
relation reinforces its weight and merges provenance, so evidence compounds.

Everything is deterministic (insertion-independent orderings, sorted
tie-breaks) so the same events always build the same graph and enumerate the
same paths (I8). Nothing here reaches the network — the graph is pure data.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Edge", "KnowledgeGraph"]


@dataclass
class Edge:
    """One weighted, sourced relation ``src ──relation──▶ dst``.

    Attributes:
        src: the origin entity.
        relation: the relation label (e.g. ``"positive_news"``).
        dst: the destination entity.
        weight: accumulated strength (reinforced on re-observation).
        provenance: sorted event ids that asserted this edge (I4).
    """

    src: str
    relation: str
    dst: str
    weight: float = 1.0
    provenance: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str, str]:
        """The identity of the relation (``src``, ``relation``, ``dst``)."""
        return (self.src, self.relation, self.dst)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "src": self.src,
            "relation": self.relation,
            "dst": self.dst,
            "weight": self.weight,
            "provenance": list(self.provenance),
        }


@dataclass
class KnowledgeGraph:
    """A directed multigraph of weighted, sourced relations."""

    _edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)

    # -- writes ---------------------------------------------------------------
    def add(
        self,
        src: str,
        relation: str,
        dst: str,
        weight: float = 1.0,
        provenance: tuple[str, ...] | list[str] = (),
    ) -> Edge:
        """Add or reinforce ``src ──relation──▶ dst``; returns the live edge."""
        key = (src, relation, dst)
        existing = self._edges.get(key)
        merged = tuple(sorted({*(existing.provenance if existing else ()), *provenance}))
        edge = Edge(
            src=src,
            relation=relation,
            dst=dst,
            weight=(existing.weight if existing else 0.0) + weight,
            provenance=merged,
        )
        self._edges[key] = edge
        return edge

    # -- reads ----------------------------------------------------------------
    @property
    def edges(self) -> list[Edge]:
        """Every edge, deterministically ordered."""
        return [self._edges[key] for key in sorted(self._edges)]

    @property
    def entities(self) -> list[str]:
        """Every node, sorted."""
        nodes: set[str] = set()
        for src, _, dst in self._edges:
            nodes.add(src)
            nodes.add(dst)
        return sorted(nodes)

    def out_edges(self, entity: str) -> list[Edge]:
        """Outgoing edges from ``entity``, strongest first (I8 tie-break)."""
        hits = [e for e in self._edges.values() if e.src == entity]
        return sorted(hits, key=lambda e: (-e.weight, e.relation, e.dst))

    def neighbors(self, entity: str) -> list[str]:
        """Distinct direct successors of ``entity``, sorted."""
        return sorted({e.dst for e in self._edges.values() if e.src == entity})

    def paths(self, src: str, dst: str, max_depth: int = 4) -> list[list[Edge]]:
        """All simple ``src ▸ … ▸ dst`` chains up to ``max_depth`` hops.

        Ranked by descending total weight then lexicographically, so the
        strongest explanation comes first and ties are deterministic (I8).
        """
        found: list[list[Edge]] = []
        queue: deque[tuple[str, list[Edge], frozenset[str]]] = deque([(src, [], frozenset({src}))])
        while queue:
            node, trail, seen = queue.popleft()
            if node == dst and trail:
                found.append(trail)
                continue
            if len(trail) >= max_depth:
                continue
            for edge in self.out_edges(node):
                if edge.dst in seen:
                    continue
                queue.append((edge.dst, [*trail, edge], seen | {edge.dst}))
        found.sort(key=lambda p: (-sum(e.weight for e in p), [e.key for e in p]))
        return found

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot (edges in deterministic order)."""
        return {"edges": [e.as_dict() for e in self.edges]}

    def __len__(self) -> int:
        return len(self._edges)
