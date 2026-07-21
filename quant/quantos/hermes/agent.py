"""Hermes — the platform's read-only communications agent (module 24).

Outbound: turns committee decisions (and regime changes, anomalies, digests)
into :class:`HermesEvent` alerts and pushes them through the
:class:`Notifier`. The alert body is the decision's **already-recorded**
explanation (I4) — Hermes never re-analyses anything.

Inbound: ``answer(question)`` retrieves matching episodes from the
:class:`DecisionArchive` through the TF-IDF memory and reports what the
record says. An :class:`LLMClient` may rephrase the summary; offline (no
client, the deterministic mock, or any backend failure) the templated
summary is the answer — retrieval never depends on a network (I6).

Hermes is **strictly read-only** (I1): this package imports no execution or
paper layer and the agent exposes no way to place an order or mutate state.
A guard test enforces both.
"""

from __future__ import annotations

from typing import Any

from quantos.committee.decision import CommitteeDecision
from quantos.explain.explainer import explain_decision
from quantos.hermes.base import HermesEvent, Notifier
from quantos.llm.client import LLMClient, MockLLMClient
from quantos.memory.archive import DecisionArchive, decision_id
from quantos.memory.rag import TfidfMemory, index_archive

__all__ = ["Hermes", "event_from_decision"]


def event_from_decision(decision: CommitteeDecision) -> HermesEvent:
    """Build the alert for one committee decision.

    A risk veto becomes a ``veto`` event (routed like the emergency it is);
    everything else is a ``decision``. The body is the recorded narrative
    (:func:`explain_decision`, I4) and the dedupe key is the decision's
    content hash, so re-announcing the same decision delivers nothing.
    """
    record = decision.as_dict()
    if decision.blocked_by_risk:
        kind, verdict = "veto", "BLOCKED BY RISK VETO"
    elif decision.approved:
        kind, verdict = "decision", f"{decision.direction.value} approved"
    else:
        kind, verdict = "decision", "STAND DOWN"
    return HermesEvent(
        kind=kind,
        title=f"{decision.symbol}: {verdict}",
        body=explain_decision(decision),
        payload={"symbol": decision.symbol, "direction": decision.direction.value},
        dedupe_key=decision_id(record),
    )


class Hermes:
    """The messenger: pushes alerts out, answers questions from the record."""

    def __init__(
        self,
        archive: DecisionArchive,
        notifier: Notifier,
        client: LLMClient | None = None,
    ) -> None:
        """
        Args:
            archive: the decision record every answer is drawn from.
            notifier: where alerts go (routing/dedupe/rate limits live there).
            client: optional LLM used only to *phrase* answers; the
                deterministic mock and any failure fall back to the template.
        """
        self.archive = archive
        self.notifier = notifier
        self.client = client
        self._memory: TfidfMemory | None = None
        self._indexed = -1

    # -- outbound --------------------------------------------------------------
    def on_event(self, event: HermesEvent) -> None:
        """Push one event through the notifier."""
        self.notifier.notify(event)

    def announce(self, decision: CommitteeDecision) -> None:
        """Alert one committee decision (veto-aware, deduped by content)."""
        self.on_event(event_from_decision(decision))

    # -- inbound ---------------------------------------------------------------
    def answer(self, question: str, k: int = 3) -> str:
        """Answer a question from the archived record — never fresh analysis.

        Retrieval is the in-house TF-IDF memory over the archive's rendered
        episodes; when nothing matches, Hermes says so honestly (I3) rather
        than inventing an answer.
        """
        hits = self._recall(question, k=k)
        if not hits:
            return f"No archived episodes match: {question!r}. The record has nothing to say yet."
        summary = self._template(question, hits)
        return self._phrase(question, summary)

    # -- internals -------------------------------------------------------------
    def _recall(self, question: str, k: int) -> list[dict[str, Any]]:
        """Query the memory, re-indexing only when the archive grew."""
        if self._memory is None or len(self.archive) != self._indexed:
            self._memory = index_archive(self.archive)
            self._indexed = len(self.archive)
        return self._memory.query(question, k=k)

    def _template(self, question: str, hits: list[dict[str, Any]]) -> str:
        """The deterministic offline answer: what the record actually says."""
        lines = [f"From the decision archive ({len(hits)} matching episode(s)):"]
        for hit in hits:
            record = self.archive.get(str(hit["id"]))
            outcome = "open"
            if record.closed:
                outcome = f"{'won' if record.won else 'lost'} (pnl {record.pnl})"
            regime = record.regime_label or "unknown regime"
            lines.append(
                f"- [{record.decision_id}] {record.direction} {record.symbol} "
                f"in {regime}; outcome: {outcome}."
            )
        return "\n".join(lines)

    def _phrase(self, question: str, summary: str) -> str:
        """Optionally rephrase via the LLM; the template survives any failure."""
        if self.client is None or isinstance(self.client, MockLLMClient):
            return summary
        prompt = (
            "You are Hermes, the read-only messenger of a quant research platform. "
            "Answer the question using ONLY the archived facts below — do not add "
            f"analysis or advice.\n\nQuestion: {question}\n\nArchived facts:\n{summary}"
        )
        try:
            phrased = self.client.complete(prompt)
        except Exception:  # noqa: BLE001 - phrasing is optional, the record is not
            return summary
        return phrased.strip() or summary
