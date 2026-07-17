"""Confidence aggregation (module 3).

Weighted aggregation of analyst opinions into a composite
:class:`ConfidenceReport`. Abstaining analysts are **excluded from the
denominator** (invariant I3): three abstentions never dilute one clear opinion,
and an all-abstain committee is simply FLAT with zero confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.committee.base import AnalystOpinion, Direction

__all__ = ["ConfidenceModel", "ConfidenceReport", "DEFAULT_WEIGHTS"]

#: Default per-category weights (the Chair trusts price-derived signals most).
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 1.0,
    "statistical": 1.0,
    "macro": 0.8,
    "onchain": 0.8,
    "sentiment": 0.6,
}


@dataclass
class ConfidenceReport:
    """The aggregated view of the committee's conviction.

    Attributes:
        direction: composite stance.
        confidence: composite conviction in [0, 1].
        agreement: weighted fraction of active analysts sharing ``direction``.
        per_category: per-category breakdown (direction, confidence, weight,
            signed score) for auditability (I4).
        abstentions: names of analysts that abstained (I3).
        n_active: number of non-abstaining opinions aggregated.
        threshold: the confidence bar that was applied.
        min_agreement: the agreement bar that was applied.
        meets_threshold: True when direction is not FLAT and both bars clear.
    """

    direction: Direction
    confidence: float
    agreement: float
    per_category: dict[str, dict[str, float | str]] = field(default_factory=dict)
    abstentions: list[str] = field(default_factory=list)
    n_active: int = 0
    threshold: float = 0.0
    min_agreement: float = 0.0
    meets_threshold: bool = False

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "direction": self.direction.value,
            "confidence": self.confidence,
            "agreement": self.agreement,
            "per_category": self.per_category,
            "abstentions": list(self.abstentions),
            "n_active": self.n_active,
            "threshold": self.threshold,
            "min_agreement": self.min_agreement,
            "meets_threshold": self.meets_threshold,
        }


class ConfidenceModel:
    """Weighted aggregation over analyst categories.

    Each active opinion contributes ``direction.sign * confidence`` scaled by
    its category weight; the weighted mean is the composite signed score. Its
    sign gives the direction (with a small FLAT dead zone), its magnitude the
    composite confidence.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        threshold: float = 0.35,
        min_agreement: float = 0.5,
        dead_zone: float = 0.05,
    ) -> None:
        """
        Args:
            weights: per-category weights; unknown categories default to 1.0.
            threshold: minimum composite confidence to clear the bar.
            min_agreement: minimum weighted agreement to clear the bar.
            dead_zone: |signed score| below which the composite is FLAT.
        """
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        self.threshold = threshold
        self.min_agreement = min_agreement
        self.dead_zone = dead_zone

    def _weight(self, category: str) -> float:
        return float(self.weights.get(category, 1.0))

    def aggregate(self, opinions: list[AnalystOpinion]) -> ConfidenceReport:
        """Aggregate opinions into a :class:`ConfidenceReport`.

        Abstentions are recorded but excluded from every average (I3).
        """
        active = [o for o in opinions if not o.abstained]
        abstentions = [o.analyst for o in opinions if o.abstained]

        if not active:
            return ConfidenceReport(
                direction=Direction.FLAT,
                confidence=0.0,
                agreement=0.0,
                abstentions=abstentions,
                n_active=0,
                threshold=self.threshold,
                min_agreement=self.min_agreement,
                meets_threshold=False,
            )

        total_weight = sum(self._weight(o.category) for o in active)
        composite = (
            sum(self._weight(o.category) * o.direction.sign * o.confidence for o in active)
            / total_weight
        )
        direction = Direction.from_sign(composite, dead_zone=self.dead_zone)
        confidence = min(1.0, abs(composite))

        agreeing_weight = sum(self._weight(o.category) for o in active if o.direction is direction)
        agreement = agreeing_weight / total_weight

        per_category = {
            o.category: {
                "analyst": o.analyst,
                "direction": o.direction.value,
                "confidence": o.confidence,
                "weight": self._weight(o.category),
                "signed_score": o.direction.sign * o.confidence,
            }
            for o in active
        }

        meets = (
            direction is not Direction.FLAT
            and confidence >= self.threshold
            and agreement >= self.min_agreement
        )
        return ConfidenceReport(
            direction=direction,
            confidence=confidence,
            agreement=agreement,
            per_category=per_category,
            abstentions=abstentions,
            n_active=len(active),
            threshold=self.threshold,
            min_agreement=self.min_agreement,
            meets_threshold=meets,
        )
