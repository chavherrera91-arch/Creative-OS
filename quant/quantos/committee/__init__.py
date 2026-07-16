"""The Investment Committee: multi-agent analysis with a Risk Manager veto.

This is the platform's differentiating feature. Specialist analysts each produce
an :class:`~quantos.committee.base.AnalystOpinion` with explicit evidence; a
:class:`~quantos.committee.confidence.ConfidenceModel` aggregates them; the
:class:`~quantos.committee.risk_manager.RiskManager` can veto; and the
:class:`~quantos.committee.chair.Chair` renders the final, auditable decision.
"""

from quantos.committee.base import (
    AnalystOpinion,
    Direction,
    Evidence,
)
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.committee.decision import CommitteeDecision

__all__ = [
    "AnalystOpinion",
    "CommitteeDecision",
    "Direction",
    "Evidence",
    "InvestmentCommittee",
    "default_committee",
]
