"""The Chair (committee president).

Synthesises the analysts' opinions, the aggregated confidence and the Risk
Manager's assessment into a final :class:`CommitteeDecision`. The rule hierarchy
is deliberately simple and auditable:

1. Any Risk Manager veto blocks the trade (direction -> FLAT).
2. Otherwise the trade is approved only if confidence *and* agreement clear their
   thresholds.
3. Otherwise the committee stands down (insufficient evidence).
"""

from __future__ import annotations

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.confidence import ConfidenceReport
from quantos.committee.decision import CommitteeDecision
from quantos.committee.risk_manager import RiskAssessment
from quantos.data.models import MarketSnapshot


class Chair:
    def decide(
        self,
        snapshot: MarketSnapshot,
        opinions: list[AnalystOpinion],
        confidence: ConfidenceReport,
        risk: RiskAssessment,
    ) -> CommitteeDecision:
        reasons: list[str] = []

        if not risk.approved:
            reasons.append("Risk Manager veto — trade blocked.")
            reasons.extend(f"veto: {v}" for v in risk.vetoes)
            return CommitteeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                price=snapshot.last_price,
                direction=Direction.FLAT,
                approved=False,
                confidence=confidence.confidence,
                blocked_by_risk=True,
                reasons=reasons,
                opinions=opinions,
                confidence_report=confidence,
                risk=risk,
            )

        if confidence.meets_threshold:
            reasons.append(
                f"Approved {confidence.direction} — composite confidence "
                f"{confidence.confidence:.0%} with {confidence.agreement:.0%} agreement."
            )
            for w in risk.warnings:
                reasons.append(f"warning: {w}")
            return CommitteeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                price=snapshot.last_price,
                direction=confidence.direction,
                approved=True,
                confidence=confidence.confidence,
                blocked_by_risk=False,
                reasons=reasons,
                opinions=opinions,
                confidence_report=confidence,
                risk=risk,
            )

        reasons.append(
            f"Stand down — evidence insufficient (confidence {confidence.confidence:.0%}, "
            f"agreement {confidence.agreement:.0%})."
        )
        return CommitteeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            price=snapshot.last_price,
            direction=Direction.FLAT,
            approved=False,
            confidence=confidence.confidence,
            blocked_by_risk=False,
            reasons=reasons,
            opinions=opinions,
            confidence_report=confidence,
            risk=risk,
        )
