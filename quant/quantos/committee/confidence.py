"""Confidence aggregation.

Turns a set of :class:`AnalystOpinion` into a single, interpretable composite:
each opinion is projected onto the directional axis, weighted by its category,
and combined. The result exposes *per-dimension* confidence, the *net* signed
conviction, and an *agreement* ratio — the three numbers the Chair needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.committee.base import AnalystOpinion, Direction


@dataclass
class ConfidenceReport:
    direction: Direction
    confidence: float  # 0..1 composite conviction in `direction`
    agreement: float  # 0..1 weighted share of participants backing `direction`
    net_signed: float  # -1..1 weighted mean signed confidence
    per_category: dict[str, float] = field(default_factory=dict)
    participants: int = 0
    abstentions: int = 0
    meets_threshold: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": str(self.direction),
            "confidence": round(self.confidence, 4),
            "agreement": round(self.agreement, 4),
            "net_signed": round(self.net_signed, 4),
            "per_category": {k: round(v, 4) for k, v in self.per_category.items()},
            "participants": self.participants,
            "abstentions": self.abstentions,
            "meets_threshold": self.meets_threshold,
        }


class ConfidenceModel:
    def __init__(
        self,
        category_weights: dict[str, float] | None = None,
        confidence_threshold: float = 0.60,
        agreement_threshold: float = 0.55,
    ) -> None:
        self.category_weights = category_weights or {}
        self.confidence_threshold = confidence_threshold
        self.agreement_threshold = agreement_threshold

    def _weight(self, category: str) -> float:
        return float(self.category_weights.get(category, 1.0))

    def aggregate(self, opinions: list[AnalystOpinion]) -> ConfidenceReport:
        active = [o for o in opinions if not o.abstained]
        abstentions = len(opinions) - len(active)

        if not active:
            return ConfidenceReport(
                direction=Direction.FLAT,
                confidence=0.0,
                agreement=0.0,
                net_signed=0.0,
                participants=0,
                abstentions=abstentions,
                meets_threshold=False,
            )

        total_w = sum(self._weight(o.category) for o in active)
        net_signed = sum(self._weight(o.category) * o.signed_confidence for o in active) / total_w

        per_category: dict[str, float] = {}
        for o in active:
            per_category[o.category] = per_category.get(o.category, 0.0) + o.signed_confidence

        direction = (
            Direction.LONG if net_signed > 0
            else Direction.SHORT if net_signed < 0
            else Direction.FLAT
        )

        # Agreement: weighted share of active analysts whose direction matches
        # the composite (ignoring those who are FLAT).
        if direction is Direction.FLAT:
            agreement = 0.0
        else:
            agreeing = sum(
                self._weight(o.category)
                for o in active
                if o.direction is direction
            )
            agreement = agreeing / total_w

        confidence = abs(net_signed)
        meets = (
            confidence >= self.confidence_threshold
            and agreement >= self.agreement_threshold
            and direction is not Direction.FLAT
        )
        return ConfidenceReport(
            direction=direction,
            confidence=confidence,
            agreement=agreement,
            net_signed=net_signed,
            per_category=per_category,
            participants=len(active),
            abstentions=abstentions,
            meets_threshold=meets,
        )
