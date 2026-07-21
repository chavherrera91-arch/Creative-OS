"""The baseline Meta-Learner (module 15).

Feeds on two evidence streams and answers one question — *what works now?*:

* :meth:`BaselineMetaLearner.ingest_lab` — Strategy Lab survivors (M5) add
  their fitness under the regime they were tested in.
* :meth:`BaselineMetaLearner.update` — closed Decision Archive outcomes (M7)
  add realised pnl for the families each decision actually considered.

``select`` then admits only strategies whose family clears the validation bar
for the current regime, with a per-family verdict recorded for the decision's
audit trail (I4). No validated family ⇒ ``MetaSelection.stand_down`` (the
pipeline's regime-aware stand-down). Deterministic throughout (I8).
"""

from __future__ import annotations

from typing import Any

from quantos.memory.archive import DecisionArchive
from quantos.meta.base import MetaSelection, RegimePerformanceTable
from quantos.regime.base import RegimeState
from quantos.strategy.lab import LabResult

__all__ = ["BaselineMetaLearner"]


class BaselineMetaLearner:
    """Regime-gated family selection over a :class:`RegimePerformanceTable`."""

    def __init__(
        self,
        table: RegimePerformanceTable | None = None,
        *,
        min_samples: int = 3,
        min_mean_score: float = 0.0,
        min_win_rate: float = 0.5,
    ) -> None:
        """
        Args:
            table: performance map to build on (fresh when omitted).
            min_samples: evidence floor before a family can validate.
            min_mean_score: validated mean score must exceed this.
            min_win_rate: validated share of positive samples.
        """
        self.table = table if table is not None else RegimePerformanceTable()
        self.min_samples = min_samples
        self.min_mean_score = min_mean_score
        self.min_win_rate = min_win_rate
        self._seen_outcomes: set[str] = set()

    # -- evidence in ----------------------------------------------------------
    def ingest_lab(self, result: LabResult) -> int:
        """Record surviving lab records under their tested regime."""
        added = 0
        for record in result.records:
            if not record.survived:
                continue
            self.table.record(record.spec.family, record.tested_regime, record.fitness)
            added += 1
        return added

    def update(self, archive: DecisionArchive) -> None:
        """Credit each closed decision's pnl to the families it considered.

        Idempotent per archived decision: an outcome is only counted once,
        so repeated calls never double-weight the table (I8).
        """
        for record in archive.closed():
            if record.decision_id in self._seen_outcomes or record.pnl is None:
                continue
            regime = record.regime_label
            if not regime:
                continue
            families = sorted(
                {str(s.get("family", "")) for s in record.strategies_considered if s.get("family")}
            )
            for family in families:
                self.table.record(family, regime, float(record.pnl))
            self._seen_outcomes.add(record.decision_id)

    # -- selection out ---------------------------------------------------------
    def select(self, regime: RegimeState | str, universe: list[Any]) -> MetaSelection:
        """Admit only strategies whose family is validated for ``regime``."""
        label = regime.label if isinstance(regime, RegimeState) else str(regime)
        validated = set(
            self.table.validated(
                label,
                min_samples=self.min_samples,
                min_mean_score=self.min_mean_score,
                min_win_rate=self.min_win_rate,
            )
        )
        selected: list[Any] = []
        report: dict[str, str] = {}
        for strategy in universe:
            spec = getattr(strategy, "spec", strategy)
            family = str(getattr(spec, "family", "generic"))
            if family in validated:
                stats = self.table.stats(family, label)
                report[family] = (
                    f"validated for {label}: mean score {stats.mean_score:+.3f}, "
                    f"win rate {stats.win_rate:.0%} over {stats.n_samples} samples"
                )
                selected.append(strategy)
            else:
                stats = self.table.stats(family, label)
                if stats.n_samples < self.min_samples:
                    report[family] = (
                        f"rejected for {label}: only {stats.n_samples} sample(s), "
                        f"need {self.min_samples}"
                    )
                else:
                    report[family] = (
                        f"rejected for {label}: mean score {stats.mean_score:+.3f} / "
                        f"win rate {stats.win_rate:.0%} below the bar"
                    )
        return MetaSelection(regime=label, selected=selected, report=report)
