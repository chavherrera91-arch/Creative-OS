"""The research pipeline — ARCHITECTURE §4 end to end (WP-7.4).

One call composes the whole regime-aware flow::

    classify regime ──▶ MetaLearner.select(regime, universe)
         │                    │ only regime-validated families survive
         │                    ▼
         │            selected strategies emit their latest signals
         ▼                    ▼
    InvestmentCommittee.deliberate(snapshot, context)
         ▼
    CommitteeDecision — records the regime, the strategies considered
    (with per-family verdicts) and the meta selection (I4)

Stand-downs are explicit and honest: an untradeable regime is handled by the
Chair's regime gate, and a tradeable regime with **no validated family** makes
the pipeline stand the decision down with the Meta-Learner's verdicts in the
reasons. The pipeline never touches capital (I1) and is deterministic for a
given snapshot + table (I8).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from quantos.committee.base import Direction
from quantos.committee.committee import InvestmentCommittee, regime_aware_committee
from quantos.committee.decision import CommitteeDecision
from quantos.config import Settings
from quantos.data.models import MarketSnapshot
from quantos.meta.base import MetaSelection
from quantos.meta.learner import BaselineMetaLearner
from quantos.regime.base import RegimeClassifier, RegimeState
from quantos.regime.classifier import RuleRegimeClassifier
from quantos.strategy.base import Strategy

__all__ = ["ResearchPipeline", "research_pipeline"]


class ResearchPipeline:
    """Regime → meta-selection → committee, as one auditable step."""

    def __init__(
        self,
        committee: InvestmentCommittee,
        classifier: RegimeClassifier,
        meta: BaselineMetaLearner,
        universe: list[Strategy] | None = None,
        *,
        require_validated: bool = True,
    ) -> None:
        """
        Args:
            committee: the deliberating bench (regime-aware or default).
            classifier: the Market Regime Engine used for the §4 first step.
            meta: the Meta-Learner that gates the strategy universe.
            universe: candidate strategies; empty means no meta gating.
            require_validated: stand down when the universe is non-empty but
                no family is validated for the regime (the §4 behaviour).
        """
        self.committee = committee
        self.classifier = classifier
        self.meta = meta
        self.universe = list(universe or [])
        self.require_validated = require_validated

    def decide(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> CommitteeDecision:
        """Run the full §4 flow on one snapshot."""
        regime = self.classifier.classify(snapshot)
        selection = self.meta.select(regime, self.universe)

        pipeline_context = dict(context or {})
        pipeline_context["regime"] = regime.as_dict()
        pipeline_context["meta_selection"] = selection.as_dict()
        pipeline_context["strategies_considered"] = self._considered(snapshot, selection)

        decision = self.committee.deliberate(snapshot, pipeline_context)
        if self._must_stand_down(regime, selection, decision):
            return self._stand_down(decision, selection)
        return decision

    # -- internals ------------------------------------------------------------
    def _considered(
        self, snapshot: MarketSnapshot, selection: MetaSelection
    ) -> list[dict[str, Any]]:
        """The selected strategies' dossier entries, signals included."""
        entries: list[dict[str, Any]] = []
        for strategy in selection.selected:
            spec = strategy.spec
            signal = float(strategy.signals(snapshot.ohlcv).iloc[-1])
            entries.append(
                {
                    "name": spec.name,
                    "key": spec.key,
                    "family": spec.family,
                    "spec_hash": spec.spec_hash(),
                    "target_regimes": list(spec.target_regimes),
                    "signal": signal,
                    "verdict": selection.report.get(spec.family, ""),
                }
            )
        return entries

    def _must_stand_down(
        self, regime: RegimeState, selection: MetaSelection, decision: CommitteeDecision
    ) -> bool:
        if not self.require_validated or not self.universe:
            return False
        if not regime.tradeable:
            return False  # the Chair's regime gate already stood down
        return selection.stand_down and decision.direction is not Direction.FLAT

    @staticmethod
    def _stand_down(decision: CommitteeDecision, selection: MetaSelection) -> CommitteeDecision:
        """Derive the meta-gated stand-down record from the deliberation."""
        verdicts = "; ".join(f"{fam}: {why}" for fam, why in sorted(selection.report.items()))
        reason = (
            f"meta-learner gate: no strategy family is validated for regime "
            f"'{selection.regime}' — standing down ({verdicts})"
        )
        return replace(
            decision,
            direction=Direction.FLAT,
            approved=False,
            reasons=[*decision.reasons, reason],
        )


def research_pipeline(
    universe: list[Strategy] | None = None,
    settings: Settings | None = None,
    meta: BaselineMetaLearner | None = None,
) -> ResearchPipeline:
    """The default §4 stack: regime-aware bench + rule classifier + baseline meta."""
    return ResearchPipeline(
        committee=regime_aware_committee(settings),
        classifier=RuleRegimeClassifier(),
        meta=meta if meta is not None else BaselineMetaLearner(),
        universe=universe,
    )
