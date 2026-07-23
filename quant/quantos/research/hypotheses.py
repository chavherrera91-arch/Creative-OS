"""Hypothesis Generator (module 23) — turn findings into research questions.

Closing the research cycle: Self-Evaluation says *what decayed*, the Auditor
says *which families are dying*, and the Knowledge Engine says *what relates to
what*. This module distils those into ranked, plain-language hypotheses
("has RSI lost predictive power in TREND_UP?", "is the breakout family dying?",
"does the ETF▸inflows link carry tradable signal?") and registers each as an
:class:`~quantos.research.experiments.Experiment` — so a question becomes a
first-class, replayable ledger entry (I8), never folklore.

The rule baseline is deterministic and offline (I6); an optional LLM proposes
extra angles behind the ``[llm]`` extra and degrades to silence on any failure
(I3). Like every M9 module it **only proposes** (ARCHITECTURE §4.1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from quantos.knowledge.base import KnowledgeEngine
from quantos.learning.audit import audit
from quantos.learning.self_eval import SelfEvalReport
from quantos.memory.archive import DecisionArchive
from quantos.research.experiments import ExperimentRegistry

__all__ = ["Hypothesis", "HypothesisGenerator"]


@dataclass
class Hypothesis:
    """One ranked research question ready to become an experiment.

    Attributes:
        question: the hypothesis in plain language.
        rationale: why the evidence raised it (I4).
        priority: ranking weight (higher first).
        tags: experiment tags (always includes ``"hypothesis"``).
        setup: the pinned setup handed to the Experiment Registry (I8).
    """

    question: str
    rationale: str
    priority: float
    tags: tuple[str, ...] = ("hypothesis",)
    setup: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "question": self.question,
            "rationale": self.rationale,
            "priority": self.priority,
            "tags": list(self.tags),
            "setup": self.setup,
        }


class HypothesisGenerator:
    """Generate and register ranked research hypotheses."""

    def __init__(self, client: Any | None = None, min_family_samples: int = 3) -> None:
        """
        Args:
            client: optional :class:`~quantos.llm.client.LLMClient` for extra
                ideation; the deterministic rule baseline runs without it.
            min_family_samples: evidence floor before proposing a dying-family
                investigation.
        """
        self.client = client
        self.min_family_samples = min_family_samples

    # -- generation -----------------------------------------------------------
    def generate(
        self,
        self_eval: SelfEvalReport | None = None,
        knowledge: KnowledgeEngine | None = None,
        archive: DecisionArchive | None = None,
    ) -> list[Hypothesis]:
        """Distil findings into ranked hypotheses (deterministic, I8)."""
        hypotheses: list[Hypothesis] = []
        if self_eval is not None:
            hypotheses.extend(self._from_self_eval(self_eval))
        if archive is not None:
            hypotheses.extend(self._from_archive(archive))
        if knowledge is not None:
            hypotheses.extend(self._from_knowledge(knowledge))
        if self.client is not None:
            hypotheses.extend(self._from_llm(self_eval, knowledge))
        return sorted(hypotheses, key=lambda h: (-h.priority, h.question))

    def _from_self_eval(self, report: SelfEvalReport) -> list[Hypothesis]:
        out: list[Hypothesis] = []
        for item in report.degrading:
            if item.kind == "signal":
                out.append(
                    Hypothesis(
                        question=f"Has indicator '{item.name}' lost predictive power?",
                        rationale=(
                            f"hit rate fell {item.earlier_hit:.0%} → {item.recent_hit:.0%} "
                            f"over {item.n_recent} recent scored calls"
                        ),
                        priority=round(0.5 + 0.5 * item.delta, 6),
                        tags=("hypothesis", "signal-decay"),
                        setup={"kind": "signal_decay", "signal": item.name, "delta": item.delta},
                    )
                )
            else:
                out.append(
                    Hypothesis(
                        question=f"Is analyst '{item.name}' still pulling its weight?",
                        rationale=(
                            f"hit rate fell {item.earlier_hit:.0%} → {item.recent_hit:.0%} "
                            f"over {item.n_recent} recent scored calls"
                        ),
                        priority=round(0.45 + 0.5 * item.delta, 6),
                        tags=("hypothesis", "analyst-decay"),
                        setup={"kind": "analyst_decay", "analyst": item.name, "delta": item.delta},
                    )
                )
        return out

    def _from_archive(self, archive: DecisionArchive) -> list[Hypothesis]:
        report = audit(archive, min_samples=self.min_family_samples)
        out: list[Hypothesis] = []
        for key, stats in report.families.items():
            if stats["n"] >= self.min_family_samples and stats["mean_pnl"] < 0.0:
                family, regime = key.split("@", 1)
                out.append(
                    Hypothesis(
                        question=f"Is the '{family}' strategy family dying in {regime}?",
                        rationale=(
                            f"mean pnl {stats['mean_pnl']:+.2f} over {stats['n']:.0f} "
                            f"closed decisions in {regime}"
                        ),
                        priority=round(0.6 + min(abs(stats["mean_pnl"]) / 100.0, 0.4), 6),
                        tags=("hypothesis", "family-decay"),
                        setup={"kind": "family_decay", "family": family, "regime": regime},
                    )
                )
        return out

    def _from_knowledge(self, knowledge: KnowledgeEngine, top_k: int = 3) -> list[Hypothesis]:
        edges = sorted(knowledge.graph.edges, key=lambda e: (-e.weight, e.src, e.dst))
        out: list[Hypothesis] = []
        for edge in edges[:top_k]:
            out.append(
                Hypothesis(
                    question=(
                        f"Does the {edge.src} ──{edge.relation}──▶ {edge.dst} link carry "
                        "tradable signal?"
                    ),
                    rationale=f"observed {edge.weight:.1f}x across {len(edge.provenance)} events",
                    priority=round(0.3 + min(edge.weight / 20.0, 0.2), 6),
                    tags=("hypothesis", "new-variable"),
                    setup={
                        "kind": "new_variable",
                        "src": edge.src,
                        "relation": edge.relation,
                        "dst": edge.dst,
                    },
                )
            )
        return out

    def _from_llm(
        self, self_eval: SelfEvalReport | None, knowledge: KnowledgeEngine | None
    ) -> list[Hypothesis]:
        if self.client is None:
            return []
        context = {
            "degrading": [i.name for i in (self_eval.degrading if self_eval else [])],
            "entities": knowledge.graph.entities if knowledge else [],
        }
        prompt = (
            "You are a quant research director. Given these findings, propose extra "
            "research hypotheses as JSON {'hypotheses': [{'question','rationale'}]}:\n"
            f"{json.dumps(context, sort_keys=True)}"
        )
        try:
            raw = self.client.complete(
                prompt, schema={"hypotheses": [{"question": "", "rationale": ""}]}
            )
            payload = json.loads(raw)
            items = payload.get("hypotheses", []) if isinstance(payload, dict) else []
        except Exception:  # noqa: BLE001 - LLM ideation is optional (I3/I6)
            return []
        out: list[Hypothesis] = []
        for item in items:
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            out.append(
                Hypothesis(
                    question=question,
                    rationale=str(item.get("rationale", "LLM-proposed")),
                    priority=0.35,
                    tags=("hypothesis", "llm"),
                    setup={"kind": "llm_ideation"},
                )
            )
        return out

    # -- registration ---------------------------------------------------------
    def register(self, registry: ExperimentRegistry, hypotheses: list[Hypothesis]) -> list[str]:
        """Register each hypothesis as an experiment; returns the ids (I8)."""
        ids: list[str] = []
        for hypothesis in hypotheses:
            ids.append(
                registry.register(
                    hypothesis.question,
                    setup={**hypothesis.setup, "priority": hypothesis.priority},
                    tags=hypothesis.tags,
                )
            )
        return ids
