"""RAG memory — recall past decisions by meaning, offline.

The default retriever is an in-house TF-IDF + cosine index (numpy only, I6):
deterministic scores, deterministic tie-breaks (I8), no external embedding
service. ``index_archive`` renders each archived decision (and its outcome)
into a searchable episode so the committee can be handed context like
"six months ago strategy 23 failed when CPI hit".

An embedding backend can replace the scorer without changing the port: pass
``embedder=`` any callable ``text -> vector`` (e.g. an ``[llm]``-extra client)
and the same index runs on cosine similarity over those vectors instead.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

import numpy as np

from quantos.memory.archive import ArchivedDecision, DecisionArchive

__all__ = ["TfidfMemory", "index_archive", "render_episode"]

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class TfidfMemory:
    """In-memory TF-IDF retriever satisfying :class:`MemoryStore` (I6/I8)."""

    def __init__(self, embedder: Callable[[str], np.ndarray] | None = None) -> None:
        """
        Args:
            embedder: optional ``text -> vector`` backend; TF-IDF when omitted.
        """
        self._docs: list[dict[str, Any]] = []
        self._tokens: list[Counter[str]] = []
        self._vectors: list[np.ndarray] = []
        self._embedder = embedder

    # -- MemoryStore ----------------------------------------------------------
    def add(self, doc: dict[str, Any]) -> str:
        """Index a document (``doc['text']`` is the searchable body)."""
        text = str(doc.get("text", ""))
        if not text:
            raise ValueError("memory documents need a non-empty 'text'")
        doc_id = doc.get("id") or f"doc-{len(self._docs):06d}"
        stored = {**doc, "id": doc_id}
        self._docs.append(stored)
        self._tokens.append(Counter(_tokenize(text)))
        if self._embedder is not None:
            self._vectors.append(np.asarray(self._embedder(text), dtype=float))
        return str(doc_id)

    def query(
        self, text: str, k: int = 5, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Best-first relevant documents; deterministic score+id ordering."""
        if not self._docs:
            return []
        scores = (
            self._embedding_scores(text) if self._embedder is not None else self._tfidf_scores(text)
        )
        ranked = sorted(
            zip(self._docs, scores, strict=True),
            key=lambda pair: (-pair[1], str(pair[0]["id"])),
        )
        out: list[dict[str, Any]] = []
        for doc, score in ranked:
            if score <= 0.0:
                continue
            if filters and any(doc.get(key) != value for key, value in filters.items()):
                continue
            out.append({**doc, "score": float(score)})
            if len(out) >= k:
                break
        return out

    def __len__(self) -> int:
        return len(self._docs)

    # -- scoring --------------------------------------------------------------
    def _idf(self, term: str) -> float:
        df = sum(1 for counts in self._tokens if term in counts)
        return math.log((1 + len(self._tokens)) / (1 + df)) + 1.0

    def _tfidf_scores(self, text: str) -> list[float]:
        query = Counter(_tokenize(text))
        if not query:
            return [0.0] * len(self._docs)
        idf = {term: self._idf(term) for term in query}
        scores: list[float] = []
        for counts in self._tokens:
            total = sum(counts.values()) or 1
            dot = sum(
                (query[t] * idf[t]) * ((counts[t] / total) * idf[t]) for t in query if t in counts
            )
            norm = math.sqrt(sum(((c / total) * self._idf(t)) ** 2 for t, c in counts.items()))
            scores.append(dot / norm if norm > 0 else 0.0)
        return scores

    def _embedding_scores(self, text: str) -> list[float]:
        assert self._embedder is not None
        q = np.asarray(self._embedder(text), dtype=float)
        qn = float(np.linalg.norm(q)) or 1.0
        return [
            float(np.dot(q, v) / (qn * (float(np.linalg.norm(v)) or 1.0))) for v in self._vectors
        ]


def render_episode(record: ArchivedDecision) -> str:
    """Flatten an archived decision (+ outcome) into a searchable narrative."""
    decision = record.decision
    parts = [
        f"{decision.get('direction', 'FLAT')} {decision.get('symbol', '')}",
        f"regime {record.regime_label}" if record.regime_label else "",
        " ".join(str(r) for r in decision.get("reasons", [])),
    ]
    for opinion in record.opinions:
        for evidence in opinion.get("evidence", []):
            parts.append(str(evidence.get("detail", "")))
    risk = decision.get("risk") or {}
    for check in risk.get("checks", []):
        parts.append(str(check.get("reason", "")))
    for strategy in record.strategies_considered:
        parts.append(f"strategy {strategy.get('name', '')} family {strategy.get('family', '')}")
    if record.closed:
        outcome = "won" if record.won else "lost"
        parts.append(f"outcome {outcome} pnl {record.pnl} {record.outcome_notes}")
    return " ".join(p for p in parts if p)


def index_archive(archive: DecisionArchive, memory: TfidfMemory | None = None) -> TfidfMemory:
    """Index every archived decision as one retrievable episode."""
    memory = memory if memory is not None else TfidfMemory()
    for record in archive.query():
        memory.add(
            {
                "id": record.decision_id,
                "text": render_episode(record),
                "symbol": record.symbol,
                "regime": record.regime_label,
                "closed": record.closed,
                "won": record.won,
            }
        )
    return memory
