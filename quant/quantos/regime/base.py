"""Market Regime Engine contracts (module 14, ARCHITECTURE §2.4).

``RegimeState`` is the explainable classification the whole platform pivots
on — "what market are we in?" — carrying the label, per-label probabilities,
the driving features and signed :class:`~quantos.committee.base.Evidence`
explaining the call (I4). ``RegimeClassifier`` is the port (I7): the rule
baseline, HMM/GMM backends and any future model all satisfy it. The
Meta-Learner (M7) will select strategy families validated for the classified
regime; until then the label feeds the Chair's regime gate directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quantos.committee.base import Evidence
from quantos.data.models import MarketSnapshot

__all__ = ["REGIME_LABELS", "UNTRADEABLE_LABELS", "RegimeClassifier", "RegimeState"]

#: The closed vocabulary of market regimes (ARCHITECTURE §2.4).
REGIME_LABELS: tuple[str, ...] = (
    "TREND_UP",
    "TREND_DOWN",
    "RANGE",
    "HIGH_VOL",
    "LOW_VOL",
    "MACRO_EVENT",
    "CRISIS",
)

#: Regimes in which the Chair's regime gate stands the committee down by
#: default (ARCHITECTURE §3 hierarchy, step 1). With the Meta-Learner (M7)
#: this becomes "regimes with no validated strategy family".
UNTRADEABLE_LABELS: frozenset[str] = frozenset({"CRISIS"})


@dataclass
class RegimeState:
    """An explainable, auditable market-state classification.

    Attributes:
        label: the winning regime, one of :data:`REGIME_LABELS`.
        probabilities: per-label probabilities (sum ≈ 1).
        features: the driving feature values (ADX, vol ratio, Hurst, ...).
        evidence: signed evidence explaining the call (I4).
        tradeable: False when the Chair's regime gate must stand down.
        as_of: point in time of the classification (never a wall clock, I2).
        classifier: name of the classifier that produced it (I8 provenance).
    """

    label: str
    probabilities: dict[str, float]
    features: dict[str, float] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    tradeable: bool = True
    as_of: str = ""
    classifier: str = ""

    def __post_init__(self) -> None:
        if self.label not in REGIME_LABELS:
            raise ValueError(f"unknown regime label {self.label!r} (expected {REGIME_LABELS})")
        unknown = set(self.probabilities) - set(REGIME_LABELS)
        if unknown:
            raise ValueError(f"unknown labels in probabilities: {sorted(unknown)}")
        total = sum(self.probabilities.values())
        if self.probabilities and not 0.99 <= total <= 1.01:
            raise ValueError(f"probabilities must sum to ~1, got {total:.4f}")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable record — what ``CommitteeDecision.regime`` stores (I4)."""
        return {
            "label": self.label,
            "probabilities": dict(self.probabilities),
            "features": dict(self.features),
            "evidence": [e.as_dict() for e in self.evidence],
            "tradeable": self.tradeable,
            "as_of": self.as_of,
            "classifier": self.classifier,
        }


@runtime_checkable
class RegimeClassifier(Protocol):
    """Port for regime classifiers (I7).

    Implementations must be deterministic — the same snapshot always yields
    the same :class:`RegimeState` (I8) — and must read only data already
    inside the snapshot (I2).
    """

    def classify(self, snapshot: MarketSnapshot) -> RegimeState:
        """Classify the market state of a snapshot."""
        ...
