"""The Decision Archive — every decision's dossier, plus its later outcome.

Vision item 10: each decision produces an "expediente" (the full
:meth:`~quantos.committee.decision.CommitteeDecision.as_dict` record — analysts,
evidence, regime, strategies considered, risk, run manifest) that is persisted
through the M2 :class:`~quantos.data.store.base.Store` and later completed with
its realised outcome (``record_outcome``). The archive is the raw material for
the Auditor (WP-7.5), the Confidence Calibrator (WP-7.6) and the Meta-Learner
(WP-7.3): closed records are how the platform learns.

Identity is content-addressed: the archive id is a hash of the decision's
canonical JSON, so recording the same decision twice is idempotent and any
archived decision can be replayed bit-for-bit from its stored manifest (I8).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from quantos.committee.decision import CommitteeDecision
from quantos.data.store import DuckDBStore, Store

__all__ = ["ArchivedDecision", "DecisionArchive"]

#: Store location of the archive (research-ready tier).
_TIER = "features"
_TABLE = "decisions"


def decision_id(record: dict[str, Any]) -> str:
    """Content-addressed identity of a decision record (I8)."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ArchivedDecision:
    """One archived decision plus (optionally) its realised outcome.

    Attributes:
        decision_id: content hash of the decision record.
        decision: the full ``CommitteeDecision.as_dict()`` dossier (I4).
        pnl: realised profit/loss once the outcome is known, else None.
        outcome_notes: free-text context recorded with the outcome.
        closed: True once an outcome has been recorded.
    """

    decision_id: str
    decision: dict[str, Any]
    pnl: float | None = None
    outcome_notes: str = ""
    closed: bool = False

    # -- convenience views used by the audit / calibration / meta consumers --
    @property
    def symbol(self) -> str:
        return str(self.decision.get("symbol", ""))

    @property
    def direction(self) -> str:
        return str(self.decision.get("direction", "FLAT"))

    @property
    def confidence(self) -> float:
        return float(self.decision.get("confidence", 0.0))

    @property
    def regime_label(self) -> str:
        return str((self.decision.get("regime") or {}).get("label", ""))

    @property
    def strategies_considered(self) -> list[dict[str, Any]]:
        return list(self.decision.get("strategies_considered") or [])

    @property
    def opinions(self) -> list[dict[str, Any]]:
        return list(self.decision.get("opinions") or [])

    @property
    def won(self) -> bool | None:
        """True/False once closed on a directional call; None otherwise."""
        if not self.closed or self.pnl is None:
            return None
        return self.pnl > 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "pnl": self.pnl,
            "outcome_notes": self.outcome_notes,
            "closed": self.closed,
        }


class DecisionArchive:
    """Persist decisions and their outcomes through the tiered ``Store``.

    In-memory by default (a rootless :class:`DuckDBStore`); hand it a rooted
    store and the archive survives restarts. All queries are deterministic
    (id-ordered) and offline (I6/I8).
    """

    def __init__(self, store: Store | None = None) -> None:
        """
        Args:
            store: destination store; a fresh in-memory store when omitted.
        """
        self._store: Store = store if store is not None else DuckDBStore()

    # -- writes ---------------------------------------------------------------
    def record(self, decision: CommitteeDecision | dict[str, Any]) -> str:
        """Archive a decision's full dossier. Idempotent; returns its id."""
        record = decision.as_dict() if isinstance(decision, CommitteeDecision) else dict(decision)
        did = decision_id(record)
        existing = self._load(did)
        if existing is not None:
            return did  # same content, same id — nothing to do
        self._upsert_row(
            ArchivedDecision(decision_id=did, decision=record),
            event_time=pd.to_datetime(record.get("as_of") or None, utc=True, errors="coerce"),
        )
        return did

    def record_outcome(self, did: str, pnl: float, notes: str = "") -> None:
        """Close an archived decision with its realised outcome.

        Raises:
            KeyError: when ``did`` is not in the archive.
        """
        row = self._load(did)
        if row is None:
            raise KeyError(f"no archived decision {did!r}")
        row.pnl = float(pnl)
        row.outcome_notes = notes
        row.closed = True
        self._upsert_row(
            row,
            event_time=pd.to_datetime(row.decision.get("as_of") or None, utc=True, errors="coerce"),
        )

    # -- reads ----------------------------------------------------------------
    def get(self, did: str) -> ArchivedDecision:
        """Fetch one archived decision by id.

        Raises:
            KeyError: when ``did`` is not in the archive.
        """
        row = self._load(did)
        if row is None:
            raise KeyError(f"no archived decision {did!r}")
        return row

    def query(
        self,
        symbol: str | None = None,
        start: Any = None,
        end: Any = None,
        regime: str | None = None,
        closed: bool | None = None,
    ) -> list[ArchivedDecision]:
        """Filter the archive by symbol, event-time window, regime and state."""
        start = None if start is None else pd.Timestamp(start, tz="UTC")
        end = None if end is None else pd.Timestamp(end, tz="UTC")
        frame = self._store.read(_TIER, _TABLE, symbol=symbol, start=start, end=end)
        rows = [self._from_frame_row(r) for _, r in frame.iterrows()] if not frame.empty else []
        if regime is not None:
            rows = [r for r in rows if r.regime_label == regime]
        if closed is not None:
            rows = [r for r in rows if r.closed is closed]
        return sorted(rows, key=lambda r: r.decision_id)

    def closed(self) -> list[ArchivedDecision]:
        """All records with a recorded outcome — the learning corpus."""
        return self.query(closed=True)

    def __len__(self) -> int:
        frame = self._store.read(_TIER, _TABLE)
        return int(len(frame))

    # -- internals ------------------------------------------------------------
    def _upsert_row(self, row: ArchivedDecision, event_time: pd.Timestamp) -> None:
        frame = pd.DataFrame(
            [
                {
                    "decision_id": row.decision_id,
                    "symbol": row.symbol,
                    "event_time": event_time,
                    "regime_label": row.regime_label,
                    "direction": row.direction,
                    "confidence": row.confidence,
                    "closed": row.closed,
                    "pnl": float("nan") if row.pnl is None else float(row.pnl),
                    "outcome_notes": row.outcome_notes,
                    "decision_json": json.dumps(row.decision, sort_keys=True, default=str),
                }
            ]
        )
        # Pin nanosecond precision so window filters compare cleanly (pandas 3
        # infers coarser units from ISO strings).
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True).astype(
            "datetime64[ns, UTC]"
        )
        self._store.upsert(_TIER, _TABLE, frame, keys=["decision_id"])

    def _load(self, did: str) -> ArchivedDecision | None:
        frame = self._store.read(_TIER, _TABLE)
        if frame.empty:
            return None
        hit = frame[frame["decision_id"] == did]
        if hit.empty:
            return None
        return self._from_frame_row(hit.iloc[0])

    @staticmethod
    def _from_frame_row(row: pd.Series) -> ArchivedDecision:
        pnl = row["pnl"]
        return ArchivedDecision(
            decision_id=str(row["decision_id"]),
            decision=json.loads(row["decision_json"]),
            pnl=None if pd.isna(pnl) else float(pnl),
            outcome_notes=str(row["outcome_notes"]),
            closed=bool(row["closed"]),
        )
