"""The Auditor — mine closed trades for what failed, and propose fixes.

Vision item 10's second half: after every batch of outcomes the Auditor asks
*which analyst was most wrong, which regime hurt, which strategy family is
dying* — and emits a structured report with **proposals** (never auto-applied
changes): weight adjustments for the
:class:`~quantos.committee.confidence.ConfidenceModel` and validation
revocations for the Meta-Learner. A human (or an explicit, logged policy)
applies them — the Auditor only argues its case (ARCHITECTURE §4.1).

Scoring an opinion against an outcome is direction-aware: on a closed
directional decision, an analyst was *right* when it agreed with a winning
call or dissented from a losing one. Abstentions and FLAT opinions are never
scored — honesty is not punished (I3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.committee.confidence import DEFAULT_WEIGHTS
from quantos.memory.archive import ArchivedDecision, DecisionArchive

__all__ = ["AnalystScore", "AuditReport", "audit"]


@dataclass
class AnalystScore:
    """One analyst's scored record over the closed corpus.

    Attributes:
        analyst: panel name (e.g. ``"Macro Analyst"``).
        category: confidence-weight category the analyst votes under.
        n_scored: opinions that could be scored against an outcome.
        n_correct: of those, how many were on the right side.
    """

    analyst: str
    category: str
    n_scored: int = 0
    n_correct: int = 0

    @property
    def hit_rate(self) -> float:
        return self.n_correct / self.n_scored if self.n_scored else 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "analyst": self.analyst,
            "category": self.category,
            "n_scored": self.n_scored,
            "n_correct": self.n_correct,
            "hit_rate": self.hit_rate,
        }


@dataclass
class AuditReport:
    """The Auditor's structured findings + proposals (I4).

    Attributes:
        n_closed: closed decisions the audit ran over.
        analysts: per-analyst scored records, worst hit-rate first.
        regimes: per-regime ``{n, mean_pnl}`` over closed decisions.
        families: per-``(family, regime)`` ``{n, mean_pnl}``.
        proposals: suggested (never auto-applied) adjustments.
    """

    n_closed: int
    analysts: list[AnalystScore] = field(default_factory=list)
    regimes: dict[str, dict[str, float]] = field(default_factory=dict)
    families: dict[str, dict[str, float]] = field(default_factory=dict)
    proposals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def worst_analyst(self) -> AnalystScore | None:
        """The scored analyst with the lowest hit rate, if any were scored."""
        return self.analysts[0] if self.analysts else None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "n_closed": self.n_closed,
            "analysts": [a.as_dict() for a in self.analysts],
            "regimes": self.regimes,
            "families": self.families,
            "proposals": list(self.proposals),
        }


def _score_opinions(record: ArchivedDecision, scores: dict[str, AnalystScore]) -> None:
    decision_direction = record.direction
    won = record.won
    if won is None or decision_direction == "FLAT":
        return
    for opinion in record.opinions:
        if opinion.get("abstained") or opinion.get("direction") == "FLAT":
            continue  # honesty is never scored against (I3)
        name = str(opinion.get("analyst", "unknown"))
        score = scores.setdefault(
            name, AnalystScore(analyst=name, category=str(opinion.get("category", "")))
        )
        agreed = opinion.get("direction") == decision_direction
        score.n_scored += 1
        if (agreed and won) or (not agreed and not won):
            score.n_correct += 1


def audit(archive: DecisionArchive, *, min_samples: int = 3) -> AuditReport:
    """Mine the closed corpus and emit findings + proposals.

    Args:
        archive: the Decision Archive to learn from.
        min_samples: evidence floor before a proposal is made.

    Returns:
        An :class:`AuditReport`, deterministic for a given archive (I8).
    """
    closed = archive.closed()
    scores: dict[str, AnalystScore] = {}
    regime_pnls: dict[str, list[float]] = {}
    family_pnls: dict[str, list[float]] = {}

    for record in closed:
        if record.pnl is None:
            continue
        _score_opinions(record, scores)
        if record.regime_label:
            regime_pnls.setdefault(record.regime_label, []).append(record.pnl)
        for strategy in record.strategies_considered:
            family = str(strategy.get("family", ""))
            if family:
                key = f"{family}@{record.regime_label or 'unknown'}"
                family_pnls.setdefault(key, []).append(record.pnl)

    analysts = sorted(scores.values(), key=lambda s: (s.hit_rate, s.analyst))
    regimes = {
        label: {"n": float(len(pnls)), "mean_pnl": sum(pnls) / len(pnls)}
        for label, pnls in sorted(regime_pnls.items())
    }
    families = {
        key: {"n": float(len(pnls)), "mean_pnl": sum(pnls) / len(pnls)}
        for key, pnls in sorted(family_pnls.items())
    }

    proposals: list[dict[str, Any]] = []
    for score in analysts:
        if score.n_scored >= min_samples and score.hit_rate < 0.5:
            current = float(DEFAULT_WEIGHTS.get(score.category, 1.0))
            proposed = round(max(current * score.hit_rate / 0.5, current * 0.25), 3)
            proposals.append(
                {
                    "kind": "analyst_weight",
                    "target": score.category,
                    "analyst": score.analyst,
                    "current": current,
                    "proposed": proposed,
                    "detail": (
                        f"{score.analyst} hit {score.hit_rate:.0%} over "
                        f"{score.n_scored} scored calls — propose lowering the "
                        f"'{score.category}' weight {current} -> {proposed}"
                    ),
                }
            )
    for key, stats in families.items():
        if stats["n"] >= min_samples and stats["mean_pnl"] < 0.0:
            family, regime = key.split("@", 1)
            proposals.append(
                {
                    "kind": "meta_validation",
                    "target": family,
                    "regime": regime,
                    "detail": (
                        f"family '{family}' averages {stats['mean_pnl']:+.2f} pnl over "
                        f"{stats['n']:.0f} closed decisions in {regime} — propose "
                        "revoking its validation there"
                    ),
                }
            )

    return AuditReport(
        n_closed=len(closed),
        analysts=analysts,
        regimes=regimes,
        families=families,
        proposals=proposals,
    )
