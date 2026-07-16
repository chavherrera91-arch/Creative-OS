"""The final, auditable committee decision object."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.confidence import ConfidenceReport
from quantos.committee.risk_manager import RiskAssessment


@dataclass
class CommitteeDecision:
    """Everything needed to understand — and later audit — one decision."""

    symbol: str
    timeframe: str
    price: float
    direction: Direction  # actionable direction (FLAT when not approved)
    approved: bool
    confidence: float
    blocked_by_risk: bool
    reasons: list[str]
    opinions: list[AnalystOpinion]
    confidence_report: ConfidenceReport
    risk: RiskAssessment
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def proposed_direction(self) -> Direction:
        """What the analysts leaned toward, before risk/threshold gating."""
        return self.confidence_report.direction

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": self.price,
            "decision": str(self.direction),
            "proposed": str(self.proposed_direction),
            "approved": self.approved,
            "blocked_by_risk": self.blocked_by_risk,
            "confidence": round(self.confidence, 4),
            "reasons": list(self.reasons),
            "confidence_report": self.confidence_report.as_dict(),
            "risk": self.risk.as_dict(),
            "opinions": [o.as_dict() for o in self.opinions],
        }
