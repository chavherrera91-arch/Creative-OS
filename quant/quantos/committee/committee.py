"""The InvestmentCommittee orchestrator.

Wires the panel of analysts, the confidence model, the Risk Manager and the
Chair into a single ``deliberate`` call. This is the public entry point used by
the CLI, the backtester and paper trading.
"""

from __future__ import annotations

from typing import Any

from quantos.committee.analysts import default_analysts
from quantos.committee.base import Analyst
from quantos.committee.chair import Chair
from quantos.committee.confidence import ConfidenceModel
from quantos.committee.decision import CommitteeDecision
from quantos.committee.risk_manager import RiskManager
from quantos.config import Settings, load_settings
from quantos.data.models import MarketSnapshot


class InvestmentCommittee:
    def __init__(
        self,
        analysts: list[Analyst] | None = None,
        confidence_model: ConfidenceModel | None = None,
        risk_manager: RiskManager | None = None,
        chair: Chair | None = None,
    ) -> None:
        self.analysts = analysts if analysts is not None else default_analysts()
        self.confidence_model = confidence_model or ConfidenceModel()
        self.risk_manager = risk_manager or RiskManager()
        self.chair = chair or Chair()

    def deliberate(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> CommitteeDecision:
        opinions = [a.analyze(snapshot, context) for a in self.analysts]
        confidence = self.confidence_model.aggregate(opinions)
        risk = self.risk_manager.assess(snapshot, context)
        return self.chair.decide(snapshot, opinions, confidence, risk)


def default_committee(settings: Settings | None = None) -> InvestmentCommittee:
    """Build a committee wired from :class:`Settings`."""
    settings = settings or load_settings()
    confidence_model = ConfidenceModel(
        category_weights=settings.committee.category_weights,
        confidence_threshold=settings.committee.confidence_threshold,
        agreement_threshold=settings.committee.agreement_threshold,
    )
    risk_manager = RiskManager(settings.risk)
    return InvestmentCommittee(
        confidence_model=confidence_model,
        risk_manager=risk_manager,
    )
