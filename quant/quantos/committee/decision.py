"""The auditable, reproducible decision record (ARCHITECTURE §2.3).

``CommitteeDecision`` is the single artifact the platform stands behind: what
was decided, why, on which evidence, under which risk view — and, from M4/M7
onward, under which regime and which validated strategies (the fields exist now
and default to empty, I7). ``as_dict()`` serialises the complete record (I4);
``run_manifest`` pins everything needed to replay it (I8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.confidence import ConfidenceReport
from quantos.committee.risk_manager import RiskAssessment

__all__ = ["CommitteeDecision"]


@dataclass
class CommitteeDecision:
    """The Chair's final, fully-auditable call.

    Attributes:
        symbol: market decided on.
        timeframe: bar timeframe of the underlying snapshot.
        price: last price at decision time.
        direction: final stance (FLAT when standing down or vetoed).
        approved: True only when the committee actually wants the trade.
        confidence: composite confidence behind the call.
        blocked_by_risk: True when a Risk Manager veto forced FLAT (I5).
        reasons: the Chair's ordered reasons for the outcome.
        opinions: every analyst opinion, including abstentions (I3/I4).
        confidence_report: the aggregated conviction view.
        risk: the Risk Manager's assessment.
        regime: active market regime (populated from M4; empty in M1).
        strategies_considered: regime-validated strategies consulted
            (populated from M7; empty in M1).
        run_manifest: everything needed to replay this decision (I8).
        as_of: timestamp of the snapshot's last bar (the decision's point in
            time — never a wall clock, I2/I8).
    """

    symbol: str
    timeframe: str
    price: float
    direction: Direction
    approved: bool
    confidence: float
    blocked_by_risk: bool
    reasons: list[str] = field(default_factory=list)
    opinions: list[AnalystOpinion] = field(default_factory=list)
    confidence_report: ConfidenceReport | None = None
    risk: RiskAssessment | None = None
    regime: dict[str, Any] = field(default_factory=dict)
    strategies_considered: list[dict[str, Any]] = field(default_factory=list)
    run_manifest: dict[str, Any] = field(default_factory=dict)
    as_of: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Complete JSON-serialisable record of the decision (I4)."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": self.price,
            "direction": self.direction.value,
            "approved": self.approved,
            "confidence": self.confidence,
            "blocked_by_risk": self.blocked_by_risk,
            "reasons": list(self.reasons),
            "opinions": [o.as_dict() for o in self.opinions],
            "confidence_report": (
                self.confidence_report.as_dict() if self.confidence_report else None
            ),
            "risk": self.risk.as_dict() if self.risk else None,
            "regime": dict(self.regime),
            "strategies_considered": list(self.strategies_considered),
            "run_manifest": dict(self.run_manifest),
            "as_of": self.as_of,
        }
