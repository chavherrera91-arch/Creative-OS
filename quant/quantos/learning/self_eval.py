"""Self-Evaluation (module 20) — the platform grades its own components.

A periodic (e.g. weekly) review that splits the closed archive into an
*earlier* and a *recent* window and asks what is **decaying**: which analysts
are losing their edge, which signals/indicators have lost predictive power.
It scores each component's directional hit rate in both windows and ranks the
biggest drops first — a structured, honest self-critique (I3/I4).

An optional health snapshot flags datasets that have gone stale. Everything
is deterministic over a given archive (I8) and reads only recorded outcomes,
never the future (I2). Like every M9 module it **only reports** — it changes
nothing (ARCHITECTURE §4.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from quantos.memory.archive import ArchivedDecision, DecisionArchive

__all__ = ["EvalItem", "SelfEvalReport", "SelfEvaluator"]


@dataclass
class EvalItem:
    """One component's earlier-vs-recent scored record.

    Attributes:
        kind: ``"analyst"`` or ``"signal"``.
        name: the component's name.
        earlier_hit: directional hit rate in the earlier window.
        recent_hit: directional hit rate in the recent window.
        n_recent: scored samples in the recent window.
    """

    kind: str
    name: str
    earlier_hit: float
    recent_hit: float
    n_recent: int

    @property
    def delta(self) -> float:
        """How much the hit rate fell (positive = degrading)."""
        return round(self.earlier_hit - self.recent_hit, 10)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "kind": self.kind,
            "name": self.name,
            "earlier_hit": self.earlier_hit,
            "recent_hit": self.recent_hit,
            "n_recent": self.n_recent,
            "delta": self.delta,
        }


@dataclass
class SelfEvalReport:
    """The self-evaluation's ranked findings (I4).

    Attributes:
        n_closed: closed decisions reviewed.
        n_earlier: decisions in the earlier window.
        n_recent: decisions in the recent window.
        analysts: analysts ranked by degradation (worst first).
        signals: signals/indicators ranked by degradation (worst first).
        datasets: health-derived stale-dataset flags (optional).
    """

    n_closed: int
    n_earlier: int = 0
    n_recent: int = 0
    analysts: list[EvalItem] = field(default_factory=list)
    signals: list[EvalItem] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)

    @property
    def degrading(self) -> list[EvalItem]:
        """All degrading components (positive delta), worst first."""
        items = [i for i in (*self.analysts, *self.signals) if i.delta > 0]
        return sorted(items, key=lambda i: (-i.delta, i.kind, i.name))

    @property
    def least_useful_analyst(self) -> EvalItem | None:
        """The analyst with the lowest recent hit rate, if any were scored."""
        if not self.analysts:
            return None
        return min(self.analysts, key=lambda i: (i.recent_hit, i.name))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "n_closed": self.n_closed,
            "n_earlier": self.n_earlier,
            "n_recent": self.n_recent,
            "analysts": [i.as_dict() for i in self.analysts],
            "signals": [i.as_dict() for i in self.signals],
            "datasets": list(self.datasets),
        }


def _direction_sign(direction: str) -> float:
    return {"LONG": 1.0, "SHORT": -1.0}.get(direction, 0.0)


def _tally_analysts(record: ArchivedDecision, tally: dict[str, list[int]]) -> None:
    won = record.won
    dsign = _direction_sign(record.direction)
    if won is None or dsign == 0.0:
        return
    for opinion in record.opinions:
        if opinion.get("abstained") or opinion.get("direction") == "FLAT":
            continue  # honesty is never scored (I3)
        name = str(opinion.get("analyst", "unknown"))
        agreed = opinion.get("direction") == record.direction
        cell = tally.setdefault(name, [0, 0])
        cell[0] += 1
        if agreed == won:
            cell[1] += 1


def _tally_signals(record: ArchivedDecision, tally: dict[str, list[int]]) -> None:
    won = record.won
    dsign = _direction_sign(record.direction)
    if won is None or dsign == 0.0:
        return
    for opinion in record.opinions:
        if opinion.get("abstained"):
            continue
        for evidence in opinion.get("evidence", []):
            impact = float(evidence.get("impact", 0.0))
            if impact == 0.0:
                continue
            name = str(evidence.get("name", "unknown"))
            agreed = (impact > 0) == (dsign > 0)
            cell = tally.setdefault(name, [0, 0])
            cell[0] += 1
            if agreed == won:
                cell[1] += 1


def _hit(cell: list[int]) -> float:
    return cell[1] / cell[0] if cell[0] else 0.0


class SelfEvaluator:
    """Split the archive in time and rank what is decaying."""

    def __init__(self, min_samples: int = 2, min_drop: float = 0.2) -> None:
        """
        Args:
            min_samples: scored samples required in *each* window to judge a
                component (avoids ranking noise).
            min_drop: hit-rate fall below which a drop is not called degrading.
        """
        self.min_samples = min_samples
        self.min_drop = min_drop

    def evaluate(
        self,
        archive: DecisionArchive,
        health: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> SelfEvalReport:
        """Review the closed corpus (+ optional health) and rank degradation."""
        closed = sorted(
            (r for r in archive.closed() if r.pnl is not None),
            key=lambda r: (str(r.decision.get("as_of", "")), r.decision_id),
        )
        mid = len(closed) // 2
        earlier, recent = closed[:mid], closed[mid:]

        analysts = self._compare(earlier, recent, _tally_analysts, "analyst")
        signals = self._compare(earlier, recent, _tally_signals, "signal")
        datasets = self._stale_datasets(health)

        return SelfEvalReport(
            n_closed=len(closed),
            n_earlier=len(earlier),
            n_recent=len(recent),
            analysts=analysts,
            signals=signals,
            datasets=datasets,
        )

    def _compare(
        self,
        earlier: list[ArchivedDecision],
        recent: list[ArchivedDecision],
        tally_fn: Any,
        kind: str,
    ) -> list[EvalItem]:
        early_tally: dict[str, list[int]] = {}
        recent_tally: dict[str, list[int]] = {}
        for record in earlier:
            tally_fn(record, early_tally)
        for record in recent:
            tally_fn(record, recent_tally)

        items: list[EvalItem] = []
        for name in sorted(set(early_tally) & set(recent_tally)):
            early, late = early_tally[name], recent_tally[name]
            if early[0] < self.min_samples or late[0] < self.min_samples:
                continue
            items.append(
                EvalItem(
                    kind=kind,
                    name=name,
                    earlier_hit=round(_hit(early), 10),
                    recent_hit=round(_hit(late), 10),
                    n_recent=late[0],
                )
            )
        return sorted(items, key=lambda i: (-i.delta, i.name))

    def _stale_datasets(self, health: Mapping[str, Mapping[str, Any]] | None) -> list[str]:
        if not health:
            return []
        stale: list[str] = []
        for name in sorted(health):
            status = health[name]
            success = float(status.get("success_rate", 1.0))
            if status.get("stale") or success < 0.5:
                stale.append(
                    f"dataset '{name}' looks stale (success rate {success:.0%}) — "
                    "may no longer add signal"
                )
        return stale
