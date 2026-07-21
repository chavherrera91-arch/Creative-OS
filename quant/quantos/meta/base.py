"""Meta-learning contracts (ARCHITECTURE §2.4, module 15).

The platform never hunts for one winning strategy: the
:class:`RegimePerformanceTable` accumulates validated evidence per
``(strategy family, regime)`` and a :class:`MetaLearner` selects, before each
decision, **only** the families proven in the current regime. No validated
family ⇒ stand down. Every selection is explainable (I4) and deterministic
(I8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quantos.regime.base import REGIME_LABELS

__all__ = ["FamilyRegimeStats", "MetaLearner", "MetaSelection", "RegimePerformanceTable"]


@dataclass
class FamilyRegimeStats:
    """Accumulated evidence for one ``(family, regime)`` cell.

    Attributes:
        family: strategy family the samples belong to.
        regime: regime label the samples were realised under.
        scores: per-sample validated scores (lab fitness, realised pnl, ...).
    """

    family: str
    regime: str
    scores: list[float] = field(default_factory=list)

    @property
    def n_samples(self) -> int:
        return len(self.scores)

    @property
    def mean_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def win_rate(self) -> float:
        if not self.scores:
            return 0.0
        return sum(1 for s in self.scores if s > 0.0) / len(self.scores)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "family": self.family,
            "regime": self.regime,
            "n_samples": self.n_samples,
            "mean_score": self.mean_score,
            "win_rate": self.win_rate,
        }


class RegimePerformanceTable:
    """The regime → strategy-family performance map (the third hard asset)."""

    def __init__(self) -> None:
        self._cells: dict[tuple[str, str], FamilyRegimeStats] = {}

    def record(self, family: str, regime: str, score: float) -> None:
        """Add one validated sample for ``(family, regime)``.

        Raises:
            ValueError: for an unknown regime label.
        """
        if regime not in REGIME_LABELS:
            raise ValueError(f"unknown regime label {regime!r} (expected {REGIME_LABELS})")
        cell = self._cells.setdefault(
            (family, regime), FamilyRegimeStats(family=family, regime=regime)
        )
        cell.scores.append(float(score))

    def stats(self, family: str, regime: str) -> FamilyRegimeStats:
        """The cell for ``(family, regime)`` (empty stats when unseen)."""
        return self._cells.get((family, regime), FamilyRegimeStats(family=family, regime=regime))

    def families(self) -> list[str]:
        """Every family with at least one sample, sorted (I8)."""
        return sorted({family for family, _ in self._cells})

    def validated(
        self,
        regime: str,
        *,
        min_samples: int = 3,
        min_mean_score: float = 0.0,
        min_win_rate: float = 0.5,
    ) -> list[str]:
        """Families whose evidence in ``regime`` clears the bar, sorted (I8)."""
        out = []
        for (family, cell_regime), cell in self._cells.items():
            if cell_regime != regime:
                continue
            if (
                cell.n_samples >= min_samples
                and cell.mean_score > min_mean_score
                and cell.win_rate >= min_win_rate
            ):
                out.append(family)
        return sorted(out)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable map ``regime -> family -> stats``."""
        table: dict[str, dict[str, Any]] = {}
        for (family, regime), cell in sorted(self._cells.items()):
            table.setdefault(regime, {})[family] = cell.as_dict()
        return table


@dataclass
class MetaSelection:
    """An explainable strategy selection for one regime (I4).

    Attributes:
        regime: the regime the selection was made for.
        selected: the strategies cleared to feed the committee.
        report: per-family verdicts — why each was chosen or rejected.
    """

    regime: str
    selected: list[Any] = field(default_factory=list)
    report: dict[str, str] = field(default_factory=dict)

    @property
    def stand_down(self) -> bool:
        """True when no strategy survived selection."""
        return not self.selected

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (strategies by spec key)."""
        return {
            "regime": self.regime,
            "selected": [getattr(getattr(s, "spec", s), "key", str(s)) for s in self.selected],
            "report": dict(self.report),
            "stand_down": self.stand_down,
        }


@runtime_checkable
class MetaLearner(Protocol):
    """Select regime-validated strategies; learn continuously from outcomes."""

    def select(self, regime: Any, universe: list[Any]) -> MetaSelection:
        """Only strategies whose family is validated for ``regime``."""
        ...

    def update(self, archive: Any) -> None:
        """Refresh the performance table from newly closed outcomes."""
        ...
