"""Debate orchestrator (ARCHITECTURE §3 debate protocol, M6 WP-6.3).

:class:`DebateCommittee` is an **alternative** orchestrator to the default
:class:`~quantos.committee.committee.InvestmentCommittee` flow: every analyst
opines independently, then sees a summary of its peers' first-round stances
and may revise **once**, and only then does the Chair decide. Deterministic
rule-based analysts simply reaffirm; an :class:`~quantos.committee.llm.LLMAnalyst`
receives the peer summary in its prompt and can genuinely change its mind.

The debate produces the **same** :class:`CommitteeDecision` type and honours
the **same** hierarchy — regime gate ▶ risk veto (absolute, I5) ▶ evidence
threshold — and the full debate record (first round, revisions) is pinned
into the decision's ``run_manifest`` and surfaced in the Chair's reasons, so
``explain_decision`` shows it (I4). The plain-Python loop is the offline
default; a LangGraph graph is optional and lazily imported (I6).
"""

from __future__ import annotations

from typing import Any

from quantos.committee.base import AnalystOpinion
from quantos.committee.committee import InvestmentCommittee
from quantos.committee.decision import CommitteeDecision
from quantos.data.models import MarketSnapshot

__all__ = ["DebateCommittee", "peer_summary"]


def peer_summary(opinions: list[AnalystOpinion]) -> list[dict[str, Any]]:
    """A compact, auditable summary of a round's stances (fed back to peers)."""
    return [
        {
            "analyst": opinion.analyst,
            "category": opinion.category,
            "direction": opinion.direction.value,
            "confidence": round(opinion.confidence, 4),
            "abstained": opinion.abstained,
            "headline": opinion.evidence[0].detail if opinion.evidence else "",
        }
        for opinion in opinions
    ]


class DebateCommittee(InvestmentCommittee):
    """Deliberation with one structured revision round before the Chair.

    Same composition surface as :class:`InvestmentCommittee` (I7) — only the
    orchestration differs. Same analysts + same snapshot + same seeds ⇒ the
    same decision (I8).
    """

    def __init__(self, *args: Any, use_langgraph: bool = False, **kwargs: Any) -> None:
        """
        Args:
            *args: forwarded to :class:`InvestmentCommittee`.
            use_langgraph: route the debate through a LangGraph state graph
                (optional dependency, lazily imported); the plain-Python
                loop — identical semantics — is the default (I6).
            **kwargs: forwarded to :class:`InvestmentCommittee`.
        """
        super().__init__(*args, **kwargs)
        self.use_langgraph = use_langgraph

    # -- debate steps (shared by both execution paths) ---------------------

    def _first_round(
        self, snapshot: MarketSnapshot, context: dict[str, Any]
    ) -> list[AnalystOpinion]:
        """Round 1: every analyst opines independently (the M1 flow)."""
        return [analyst.analyze(snapshot, context) for analyst in self.analysts]

    def _revision_round(
        self,
        snapshot: MarketSnapshot,
        context: dict[str, Any],
        first: list[AnalystOpinion],
    ) -> tuple[list[AnalystOpinion], dict[str, Any]]:
        """Round 2: each analyst sees the peer summary and may revise once."""
        debate_context = {
            **context,
            "debate": {"round": 2, "peer_summary": peer_summary(first)},
        }
        final = [analyst.analyze(snapshot, debate_context) for analyst in self.analysts]
        return final, debate_context

    def _decide(
        self,
        snapshot: MarketSnapshot,
        debate_context: dict[str, Any],
        first: list[AnalystOpinion],
        final: list[AnalystOpinion],
    ) -> CommitteeDecision:
        """Aggregate the revised round and apply the unchanged hierarchy.

        Regime gate ▶ risk veto ▶ threshold live in the Chair exactly as in
        the default flow — the debate changes *inputs*, never the rules (I5).
        """
        revised = [
            after.analyst
            for before, after in zip(first, final, strict=True)
            if before.as_dict() != after.as_dict()
        ]
        manifest = self._run_manifest(snapshot)
        manifest["debate"] = {
            "protocol": "peer-summary-revise-once",
            "orchestrator": "langgraph" if self.use_langgraph else "python",
            "rounds": 2,
            "first_round": [opinion.as_dict() for opinion in first],
            "revised": revised,
        }
        report = self.confidence_model.aggregate(final)
        risk = self.risk_manager.assess(snapshot, report, debate_context)
        decision = self.chair.decide(
            snapshot, final, report, risk, context=debate_context, run_manifest=manifest
        )
        decision.reasons.append(
            f"debate protocol: {len(self.analysts)} analysts saw peer summaries and could "
            f"revise once — {len(revised)} revised"
            + (f" ({', '.join(revised)})" if revised else "")
        )
        return decision

    # -- execution paths ---------------------------------------------------

    def _deliberate_python(
        self, snapshot: MarketSnapshot, context: dict[str, Any]
    ) -> CommitteeDecision:
        """The dependency-free debate loop (offline default, I6)."""
        first = self._first_round(snapshot, context)
        final, debate_context = self._revision_round(snapshot, context, first)
        return self._decide(snapshot, debate_context, first, final)

    def _deliberate_langgraph(
        self, snapshot: MarketSnapshot, context: dict[str, Any]
    ) -> CommitteeDecision:
        """The same debate as a LangGraph state graph (optional, lazy).

        Raises:
            ImportError: when ``langgraph`` is not installed — the
                plain-Python loop is always available instead.
        """
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise ImportError(
                "the LangGraph debate path needs langgraph "
                "(pip install 'quantos[llm]'); use_langgraph=False runs the "
                "identical plain-Python loop offline"
            ) from exc

        def first_round(state: dict[str, Any]) -> dict[str, Any]:
            return {"first": self._first_round(snapshot, context)}

        def revision(state: dict[str, Any]) -> dict[str, Any]:
            final, debate_context = self._revision_round(snapshot, context, state["first"])
            return {"final": final, "debate_context": debate_context}

        def decide(state: dict[str, Any]) -> dict[str, Any]:
            return {
                "decision": self._decide(
                    snapshot, state["debate_context"], state["first"], state["final"]
                )
            }

        graph = StateGraph(dict)
        graph.add_node("first_round", first_round)
        graph.add_node("revision", revision)
        graph.add_node("decide", decide)
        graph.add_edge(START, "first_round")
        graph.add_edge("first_round", "revision")
        graph.add_edge("revision", "decide")
        graph.add_edge("decide", END)
        state = graph.compile().invoke({})
        decision: CommitteeDecision = state["decision"]
        return decision

    # -- the orchestrator contract ------------------------------------------

    def deliberate(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> CommitteeDecision:
        """Run the two-round debate and return the Chair's decision.

        Args:
            snapshot: the market view (analysts read only what is inside, I2).
            context: optional orchestration context, enriched exactly as in
                the default flow (``regime``, ``anomalies``, ...).

        Returns:
            The same auditable, reproducible :class:`CommitteeDecision` type
            as the default orchestrator, with the debate recorded (I4).
        """
        enriched = self._enrich_context(snapshot, context)
        if self.use_langgraph:
            return self._deliberate_langgraph(snapshot, enriched)
        return self._deliberate_python(snapshot, enriched)
