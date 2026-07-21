"""The :class:`MemoryStore` port (ARCHITECTURE §2.4, module 12).

A memory holds free-text-searchable documents — archived decisions, audit
findings, regime episodes — and answers natural queries like "what happened
last time CPI hit?". The offline default is the in-house TF-IDF retriever in
:mod:`quantos.memory.rag`; embedding-backed memories plug into the same port.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["MemoryStore"]


@runtime_checkable
class MemoryStore(Protocol):
    """Add documents, retrieve the most relevant ones for a text query."""

    def add(self, doc: dict[str, Any]) -> str:
        """Index a document; returns its id. ``doc['text']`` is the searchable
        body; every other key is stored as metadata and usable as a filter."""
        ...

    def query(
        self, text: str, k: int = 5, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """The ``k`` most relevant documents for ``text``, best first."""
        ...
