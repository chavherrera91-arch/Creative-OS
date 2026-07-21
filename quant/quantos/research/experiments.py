"""The Experiment Registry (module 19) — a scientific-lab ledger.

Every research question becomes a first-class record::

    hypothesis ──▶ experiment (setup pinned) ──▶ result ──▶ conclusion

Strategy Lab runs (M5) and Auditor findings (WP-7.5) register here so the
platform's learning is a searchable ledger, not folklore. Identity is a
content hash of ``(hypothesis, setup)`` — registering the same experiment
twice is idempotent, and the pinned setup makes every completed experiment
replayable (I8). A completed experiment is **immutable**: conclusions are
never silently rewritten.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.data.store import DuckDBStore, Store

__all__ = ["Experiment", "ExperimentRegistry"]

_TIER = "features"
_TABLE = "experiments"


def _experiment_id(hypothesis: str, setup: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"hypothesis": hypothesis, "setup": setup},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class Experiment:
    """One ledger entry: a hypothesis, its pinned setup, and its verdict.

    Attributes:
        experiment_id: content hash of ``(hypothesis, setup)`` (I8).
        hypothesis: the question being tested, in plain language.
        setup: everything needed to replay the test (seeds, params, data ids).
        tags: free labels for querying (e.g. ``("strategy-lab", "regime")``).
        status: ``"open"`` or ``"completed"``.
        result: measured outcome once completed.
        conclusion: the recorded verdict once completed.
    """

    experiment_id: str
    hypothesis: str
    setup: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    status: str = "open"
    result: dict[str, Any] = field(default_factory=dict)
    conclusion: str = ""

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "setup": self.setup,
            "tags": list(self.tags),
            "status": self.status,
            "result": self.result,
            "conclusion": self.conclusion,
        }


class ExperimentRegistry:
    """Register, complete and query experiments over the tiered ``Store``."""

    def __init__(self, store: Store | None = None) -> None:
        """
        Args:
            store: destination store; a fresh in-memory store when omitted.
        """
        self._store: Store = store if store is not None else DuckDBStore()

    # -- writes ---------------------------------------------------------------
    def register(
        self, hypothesis: str, setup: dict[str, Any] | None = None, tags: tuple[str, ...] = ()
    ) -> str:
        """Open an experiment; idempotent on ``(hypothesis, setup)`` (I8).

        Raises:
            ValueError: for an empty hypothesis.
        """
        if not hypothesis.strip():
            raise ValueError("an experiment needs a hypothesis")
        setup = dict(setup or {})
        experiment_id = _experiment_id(hypothesis, setup)
        if self._load(experiment_id) is not None:
            return experiment_id  # already registered (possibly completed)
        self._save(
            Experiment(
                experiment_id=experiment_id,
                hypothesis=hypothesis,
                setup=setup,
                tags=tuple(tags),
            )
        )
        return experiment_id

    def complete(self, experiment_id: str, result: dict[str, Any], conclusion: str) -> None:
        """Record the result + conclusion, sealing the experiment.

        Raises:
            KeyError: for an unknown experiment.
            ValueError: when the experiment is already completed (immutable).
        """
        experiment = self._load(experiment_id)
        if experiment is None:
            raise KeyError(f"no experiment {experiment_id!r}")
        if experiment.completed:
            raise ValueError(
                f"experiment {experiment_id!r} is completed — conclusions are immutable"
            )
        experiment.status = "completed"
        experiment.result = dict(result)
        experiment.conclusion = conclusion
        self._save(experiment)

    # -- reads ----------------------------------------------------------------
    def get(self, experiment_id: str) -> Experiment:
        """Fetch one experiment.

        Raises:
            KeyError: for an unknown experiment.
        """
        experiment = self._load(experiment_id)
        if experiment is None:
            raise KeyError(f"no experiment {experiment_id!r}")
        return experiment

    def query(
        self, status: str | None = None, tag: str | None = None, text: str | None = None
    ) -> list[Experiment]:
        """Filter the ledger by status, tag and/or hypothesis substring."""
        frame = self._store.read(_TIER, _TABLE)
        experiments = (
            [self._from_row(row) for _, row in frame.iterrows()] if not frame.empty else []
        )
        if status is not None:
            experiments = [e for e in experiments if e.status == status]
        if tag is not None:
            experiments = [e for e in experiments if tag in e.tags]
        if text is not None:
            needle = text.lower()
            experiments = [e for e in experiments if needle in e.hypothesis.lower()]
        return sorted(experiments, key=lambda e: e.experiment_id)

    def __len__(self) -> int:
        return int(len(self._store.read(_TIER, _TABLE)))

    # -- internals ------------------------------------------------------------
    def _save(self, experiment: Experiment) -> None:
        frame = pd.DataFrame([{**experiment.as_dict(), "payload": ""}])
        frame["payload"] = json.dumps(experiment.as_dict(), sort_keys=True, default=str)
        frame = frame[["experiment_id", "status", "payload"]]
        self._store.upsert(_TIER, _TABLE, frame, keys=["experiment_id"])

    def _load(self, experiment_id: str) -> Experiment | None:
        frame = self._store.read(_TIER, _TABLE)
        if frame.empty:
            return None
        hit = frame[frame["experiment_id"] == experiment_id]
        if hit.empty:
            return None
        return self._from_row(hit.iloc[0])

    @staticmethod
    def _from_row(row: pd.Series) -> Experiment:
        payload = json.loads(row["payload"])
        return Experiment(
            experiment_id=payload["experiment_id"],
            hypothesis=payload["hypothesis"],
            setup=payload["setup"],
            tags=tuple(payload.get("tags", ())),
            status=payload["status"],
            result=payload.get("result", {}),
            conclusion=payload.get("conclusion", ""),
        )
