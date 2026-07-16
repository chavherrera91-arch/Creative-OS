"""Core types shared across the committee: directions, evidence, opinions."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from quantos.data.models import MarketSnapshot


class Direction(enum.Enum):
    LONG = 1
    FLAT = 0
    SHORT = -1

    @property
    def sign(self) -> int:
        return int(self.value)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


@dataclass(frozen=True)
class Evidence:
    """A single, human-readable reason backing an opinion.

    ``impact`` is a signed contribution in roughly [-1, 1] where positive favours
    LONG and negative favours SHORT — this is what makes decisions auditable.
    """

    name: str
    detail: str
    impact: float = 0.0
    value: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "impact": round(self.impact, 4),
            "value": self.value,
        }


@dataclass
class AnalystOpinion:
    """One analyst's verdict for one snapshot."""

    analyst: str
    category: str
    direction: Direction
    confidence: float  # 0..1, how strongly the analyst holds this direction
    evidence: list[Evidence] = field(default_factory=list)
    abstained: bool = False  # True when the analyst lacked data to judge

    def __post_init__(self) -> None:
        self.confidence = float(min(1.0, max(0.0, self.confidence)))

    @property
    def signed_confidence(self) -> float:
        """Confidence projected onto the directional axis (-1..1)."""
        return self.direction.sign * self.confidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "analyst": self.analyst,
            "category": self.category,
            "direction": str(self.direction),
            "confidence": round(self.confidence, 4),
            "abstained": self.abstained,
            "evidence": [e.as_dict() for e in self.evidence],
        }


class Analyst(ABC):
    """Base class for a specialist analyst."""

    name: str = "analyst"
    category: str = "generic"

    @abstractmethod
    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        ...

    # Convenience constructors keep subclasses terse.
    def _opinion(
        self,
        direction: Direction,
        confidence: float,
        evidence: list[Evidence],
        *,
        abstained: bool = False,
    ) -> AnalystOpinion:
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=direction,
            confidence=confidence,
            evidence=evidence,
            abstained=abstained,
        )

    def _abstain(self, reason: str) -> AnalystOpinion:
        return self._opinion(
            Direction.FLAT,
            0.0,
            [Evidence("no_data", reason, 0.0)],
            abstained=True,
        )
