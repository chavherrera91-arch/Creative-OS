"""Confidence Calibration (module 18) — is the stated confidence honest?

A committee can say "90%" and win only 60% of the time. The
:class:`ConfidenceCalibrator` learns the stated-vs-realised map from the
closed Decision Archive (binned reliability, monotonically regularised,
optionally per-regime) and corrects raw confidence before the Chair applies
its threshold. Until enough history exists it is the **identity** map — the
calibrator never invents information it does not have (cold start, I3 in
spirit).

Wiring is plug-in (I7): :class:`CalibratedConfidenceModel` subclasses the M1
:class:`~quantos.committee.confidence.ConfidenceModel`, so it drops into
``InvestmentCommittee(confidence_model=...)`` with zero core edits. The
report it returns carries the calibrated composite; ``meets_threshold`` is
re-evaluated against the same bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.confidence import ConfidenceModel, ConfidenceReport
from quantos.memory.archive import DecisionArchive

__all__ = ["CalibratedConfidenceModel", "ConfidenceCalibrator"]


@dataclass
class _BinTable:
    """Reliability bins for one context (global or one regime)."""

    n: np.ndarray
    stated_sum: np.ndarray
    won_sum: np.ndarray

    @classmethod
    def empty(cls, n_bins: int) -> _BinTable:
        return cls(
            n=np.zeros(n_bins, dtype=int),
            stated_sum=np.zeros(n_bins),
            won_sum=np.zeros(n_bins),
        )

    def add(self, bin_index: int, stated: float, won: bool) -> None:
        self.n[bin_index] += 1
        self.stated_sum[bin_index] += stated
        self.won_sum[bin_index] += 1.0 if won else 0.0

    def rates(self, min_samples: int) -> np.ndarray:
        """Per-bin realised win rate, monotonically regularised (NaN = no data)."""
        with np.errstate(invalid="ignore"):
            raw = np.where(self.n >= min_samples, self.won_sum / np.maximum(self.n, 1), np.nan)
        # Monotonic: higher stated confidence never maps below lower stated.
        out = raw.copy()
        running = -np.inf
        for i, value in enumerate(out):
            if np.isnan(value):
                continue
            running = max(running, value)
            out[i] = running
        return out


@dataclass
class ConfidenceCalibrator:
    """Binned stated-vs-realised reliability map over the closed archive.

    Attributes:
        n_bins: number of equal-width confidence bins over [0, 1].
        min_samples: evidence floor per bin before it overrides identity.
    """

    n_bins: int = 10
    min_samples: int = 5
    _global: _BinTable | None = field(default=None, repr=False)
    _by_regime: dict[str, _BinTable] = field(default_factory=dict, repr=False)

    # -- fitting --------------------------------------------------------------
    def fit(self, archive: DecisionArchive) -> ConfidenceCalibrator:
        """Learn the reliability map from closed directional decisions."""
        table = _BinTable.empty(self.n_bins)
        by_regime: dict[str, _BinTable] = {}
        for record in archive.closed():
            won = record.won
            if won is None or record.direction == "FLAT":
                continue
            stated = float(np.clip(record.confidence, 0.0, 1.0))
            index = self._bin(stated)
            table.add(index, stated, won)
            if record.regime_label:
                by_regime.setdefault(record.regime_label, _BinTable.empty(self.n_bins)).add(
                    index, stated, won
                )
        self._global = table
        self._by_regime = by_regime
        return self

    @property
    def fitted(self) -> bool:
        """True once at least one bin has cleared the evidence floor."""
        return self._global is not None and bool((self._global.n >= self.min_samples).any())

    # -- mapping --------------------------------------------------------------
    def calibrate(self, raw: float, context: dict[str, Any] | None = None) -> float:
        """Map stated confidence to its historically realised rate.

        Identity when unfitted or when no bin near ``raw`` has evidence; the
        regime-specific map wins over the global one when the decision's
        context names a regime with enough samples (regime-aware).
        """
        raw = float(np.clip(raw, 0.0, 1.0))
        if not self.fitted:
            return raw
        regime = str(((context or {}).get("regime") or {}).get("label", ""))
        for table in self._tables_for(regime):
            value = self._lookup(table, raw)
            if value is not None:
                return value
        return raw

    def reliability(self) -> list[dict[str, float]]:
        """Stated-vs-realised bins for the dashboard (global map)."""
        if self._global is None:
            return []
        rates = self._global.rates(self.min_samples)
        out = []
        for i in range(self.n_bins):
            n = int(self._global.n[i])
            out.append(
                {
                    "bin_low": i / self.n_bins,
                    "bin_high": (i + 1) / self.n_bins,
                    "n": float(n),
                    "stated_mean": float(self._global.stated_sum[i] / n) if n else float("nan"),
                    "realised_rate": float(rates[i]),
                }
            )
        return out

    # -- internals ------------------------------------------------------------
    def _bin(self, value: float) -> int:
        return min(int(value * self.n_bins), self.n_bins - 1)

    def _tables_for(self, regime: str) -> list[_BinTable]:
        tables: list[_BinTable] = []
        if regime and regime in self._by_regime:
            tables.append(self._by_regime[regime])
        if self._global is not None:
            tables.append(self._global)
        return tables

    def _lookup(self, table: _BinTable, raw: float) -> float | None:
        rates = table.rates(self.min_samples)
        index = self._bin(raw)
        if not np.isnan(rates[index]):
            return float(rates[index])
        populated = np.flatnonzero(~np.isnan(rates))
        if populated.size == 0:
            return None
        nearest = int(populated[np.argmin(np.abs(populated - index))])
        return float(rates[nearest])


class CalibratedConfidenceModel(ConfidenceModel):
    """A drop-in :class:`ConfidenceModel` whose composite is calibrated (I7)."""

    def __init__(
        self,
        calibrator: ConfidenceCalibrator,
        weights: dict[str, float] | None = None,
        threshold: float = 0.35,
        min_agreement: float = 0.5,
    ) -> None:
        """
        Args:
            calibrator: the fitted (or cold-start identity) reliability map.
            weights: per-category weights, as in the base model.
            threshold: confidence bar, re-applied after calibration.
            min_agreement: agreement bar, unchanged by calibration.
        """
        super().__init__(weights=weights, threshold=threshold, min_agreement=min_agreement)
        self.calibrator = calibrator
        self._context: dict[str, Any] | None = None

    def with_context(self, context: dict[str, Any] | None) -> CalibratedConfidenceModel:
        """Set the deliberation context (regime) the next aggregate maps under."""
        self._context = context
        return self

    def aggregate(self, opinions: list[AnalystOpinion]) -> ConfidenceReport:
        """Aggregate as usual, then calibrate the composite (raw → realised)."""
        report = super().aggregate(opinions)
        calibrated = self.calibrator.calibrate(report.confidence, self._context)
        meets = (
            report.direction is not Direction.FLAT
            and calibrated >= self.threshold
            and report.agreement >= self.min_agreement
        )
        return replace(report, confidence=calibrated, meets_threshold=meets)
