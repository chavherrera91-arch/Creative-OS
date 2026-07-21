"""WP-7.2 — RAG memory: TF-IDF recall over archived decisions, offline (I6/I8)."""

from __future__ import annotations

import numpy as np
import pytest

from quantos.memory import DecisionArchive, MemoryStore, TfidfMemory, index_archive
from tests.test_archive import fake_record


def seeded_archive() -> DecisionArchive:
    archive = DecisionArchive()
    cpi = fake_record("BTC/USDT", "2024-01-15T00:00:00+00:00", "MACRO_EVENT")
    cpi["reasons"] = ["strategy 23 long into the CPI print", "macro event gate warned"]
    cpi_id = archive.record(cpi)
    archive.record_outcome(cpi_id, pnl=-40.0, notes="CPI surprise crushed the position")

    trend = fake_record("BTC/USDT", "2024-02-15T00:00:00+00:00", "TREND_UP")
    trend["reasons"] = ["clean uptrend continuation, EMA structure intact"]
    archive.record(trend)

    whale = fake_record("ETH/USDT", "2024-03-15T00:00:00+00:00", "RANGE")
    whale["reasons"] = ["whale accumulation while price ranges"]
    archive.record(whale)
    return archive


class TestTfidfMemory:
    def test_satisfies_memory_store_port(self) -> None:
        assert isinstance(TfidfMemory(), MemoryStore)

    def test_requires_text(self) -> None:
        with pytest.raises(ValueError):
            TfidfMemory().add({"symbol": "BTC/USDT"})

    def test_relevance_ordering_and_determinism(self) -> None:
        memory = TfidfMemory()
        memory.add({"id": "a", "text": "CPI shock macro event losses"})
        memory.add({"id": "b", "text": "steady uptrend momentum entry"})
        memory.add({"id": "c", "text": "CPI print again, another macro drawdown"})
        first = memory.query("what happened around CPI?")
        second = memory.query("what happened around CPI?")
        assert [d["id"] for d in first] == [d["id"] for d in second]  # I8
        assert {d["id"] for d in first} == {"a", "c"}  # only CPI docs match
        assert first[0]["score"] >= first[-1]["score"]

    def test_filters_restrict_results(self) -> None:
        memory = TfidfMemory()
        memory.add({"id": "a", "text": "CPI macro loss", "symbol": "BTC/USDT"})
        memory.add({"id": "b", "text": "CPI macro loss", "symbol": "ETH/USDT"})
        hits = memory.query("CPI", filters={"symbol": "ETH/USDT"})
        assert [d["id"] for d in hits] == ["b"]

    def test_pluggable_embedder_backend(self) -> None:
        def embedder(text: str) -> np.ndarray:  # toy 2-d "embedding"
            return np.array([float("cpi" in text.lower()), float("trend" in text.lower())])

        memory = TfidfMemory(embedder=embedder)
        memory.add({"id": "macro", "text": "CPI shock"})
        memory.add({"id": "tf", "text": "trend day"})
        assert memory.query("cpi surprise")[0]["id"] == "macro"


class TestArchiveRecall:
    def test_cpi_episode_is_recalled(self) -> None:
        """The vision acceptance: query('CPI') finds the CPI-tagged decision."""
        memory = index_archive(seeded_archive())
        assert len(memory) == 3
        hits = memory.query("CPI")
        assert hits, "CPI episode must be retrievable"
        top = hits[0]
        assert top["regime"] == "MACRO_EVENT"
        assert top["won"] is False  # the outcome rides along with the episode
        assert all(h["regime"] == "MACRO_EVENT" for h in hits)

    def test_recall_can_filter_to_closed_losses(self) -> None:
        memory = index_archive(seeded_archive())
        losses = memory.query("CPI macro", filters={"closed": True, "won": False})
        assert len(losses) == 1
