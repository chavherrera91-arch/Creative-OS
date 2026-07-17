"""Committee core types (ARCHITECTURE §2.3).

``Direction``, ``Evidence`` and ``AnalystOpinion`` are the vocabulary every
agent speaks; ``Analyst`` is the ABC each specialist implements. An analyst
with no data for its channel **abstains honestly** via ``_abstain`` — it never
fabricates conviction (invariant I3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quantos.data.models import MarketSnapshot

__all__ = ["Analyst", "AnalystOpinion", "Direction", "Evidence"]


class Direction(Enum):
    """The three possible stances on a market."""

    LONG = "LONG"
    FLAT = "FLAT"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        """Numeric sign: LONG=+1, FLAT=0, SHORT=-1."""
        return {"LONG": 1, "FLAT": 0, "SHORT": -1}[self.value]

    @classmethod
    def from_sign(cls, value: float, dead_zone: float = 0.0) -> Direction:
        """Map a signed score to a direction, with an optional FLAT dead zone."""
        if value > dead_zone:
            return cls.LONG
        if value < -dead_zone:
            return cls.SHORT
        return cls.FLAT


@dataclass(frozen=True)
class Evidence:
    """One signed, auditable piece of evidence behind an opinion.

    Attributes:
        name: short identifier, e.g. ``"ema_trend"``.
        detail: human-readable explanation of what was observed.
        impact: signed contribution in [-1, +1] (positive = bullish).
        value: the raw measured value, when there is one.
    """

    name: str
    detail: str
    impact: float
    value: float | None = None

    def __post_init__(self) -> None:
        if not -1.0 <= self.impact <= 1.0:
            raise ValueError(f"Evidence.impact must be in [-1, 1], got {self.impact}")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "name": self.name,
            "detail": self.detail,
            "impact": self.impact,
            "value": self.value,
        }


@dataclass
class AnalystOpinion:
    """A specialist's stance, with the evidence that produced it.

    Attributes:
        analyst: the emitting analyst's name.
        category: analyst category (``technical``, ``macro``, ...).
        direction: the stance.
        confidence: conviction in [0, 1] (0 when abstained).
        evidence: the signed evidence trail — never empty (I4).
        abstained: True when the analyst had no usable data (I3).
    """

    analyst: str
    category: str
    direction: Direction
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    abstained: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.abstained and self.confidence != 0.0:
            raise ValueError("an abstaining analyst cannot claim confidence (I3)")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "analyst": self.analyst,
            "category": self.category,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "evidence": [e.as_dict() for e in self.evidence],
            "abstained": self.abstained,
        }


class Analyst(ABC):
    """Base class for committee specialists.

    Subclasses implement :meth:`analyze` and emit an :class:`AnalystOpinion`
    built either from evidence (:meth:`_from_evidence`) or by honest
    abstention (:meth:`_abstain`).
    """

    def __init__(self, name: str, category: str) -> None:
        self.name = name
        self.category = category

    @abstractmethod
    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        """Study a snapshot (and optional context) and return an opinion.

        Implementations must be deterministic (I8) and must only read data
        already inside the snapshot — never fetch, never look ahead (I2).
        """

    def _abstain(self, reason: str) -> AnalystOpinion:
        """Return an honest abstention (I3): FLAT, zero confidence, reason logged."""
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.FLAT,
            confidence=0.0,
            evidence=[Evidence(name="abstention", detail=reason, impact=0.0)],
            abstained=True,
        )

    def _from_evidence(self, evidence: list[Evidence], dead_zone: float = 0.15) -> AnalystOpinion:
        """Aggregate signed evidence into a direction + confidence.

        The net impact (mean of signed impacts) sets the direction — inside the
        ``dead_zone`` the stance is FLAT — and its magnitude is the confidence.
        """
        if not evidence:
            return self._abstain("no evidence produced")
        net = sum(e.impact for e in evidence) / len(evidence)
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.from_sign(net, dead_zone=dead_zone),
            confidence=min(1.0, abs(net)),
            evidence=evidence,
        )
