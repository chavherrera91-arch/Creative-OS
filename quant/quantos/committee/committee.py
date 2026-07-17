"""The Investment Committee orchestrator (module 2, M1 flow).

Analysts run independently, the confidence model aggregates, the Risk Manager
screens, the Chair decides — simple and fully deterministic (the optional
debate protocol is M6). ``default_committee()`` wires the standard bench.
"""

from __future__ import annotations

from typing import Any

import quantos
from quantos.committee.analysts import default_analysts
from quantos.committee.base import Analyst
from quantos.committee.chair import Chair
from quantos.committee.confidence import ConfidenceModel
from quantos.committee.decision import CommitteeDecision
from quantos.committee.risk_manager import RiskManager
from quantos.config import Settings
from quantos.data.models import MarketSnapshot

__all__ = ["InvestmentCommittee", "default_committee"]


class InvestmentCommittee:
    """Composes analysts, confidence model, risk manager and chair (I7)."""

    def __init__(
        self,
        analysts: list[Analyst],
        confidence_model: ConfidenceModel | None = None,
        risk_manager: RiskManager | None = None,
        chair: Chair | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.analysts = analysts
        self.confidence_model = confidence_model or ConfidenceModel(
            threshold=self.settings.confidence_threshold,
            min_agreement=self.settings.min_agreement,
        )
        self.risk_manager = risk_manager or RiskManager()
        self.chair = chair or Chair()

    def _run_manifest(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        """Pin everything needed to replay this deliberation (I8).

        Deterministic on purpose: derived from the snapshot's own point in
        time, never from a wall clock.
        """
        return {
            "quantos_version": quantos.__version__,
            "seed": self.settings.seed,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "bars": snapshot.bars,
            "as_of": snapshot.as_of,
            "analysts": [a.name for a in self.analysts],
            "weights": dict(self.confidence_model.weights),
            "confidence_threshold": self.confidence_model.threshold,
            "min_agreement": self.confidence_model.min_agreement,
            "settings": self.settings.as_dict(),
        }

    def deliberate(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> CommitteeDecision:
        """Run the full M1 decision flow on a snapshot.

        Args:
            snapshot: the market view (analysts read only what is inside, I2).
            context: optional orchestration context (``regime``,
                ``daily_pnl_pct``, ``macro_event``, ``strategies_considered``...).

        Returns:
            A complete, auditable, reproducible :class:`CommitteeDecision`.
        """
        opinions = [analyst.analyze(snapshot, context) for analyst in self.analysts]
        report = self.confidence_model.aggregate(opinions)
        risk = self.risk_manager.assess(snapshot, report, context)
        return self.chair.decide(
            snapshot,
            opinions,
            report,
            risk,
            context=context,
            run_manifest=self._run_manifest(snapshot),
        )


def default_committee(settings: Settings | None = None) -> InvestmentCommittee:
    """The standard M1 committee: five specialists, default thresholds."""
    return InvestmentCommittee(analysts=default_analysts(), settings=settings)
