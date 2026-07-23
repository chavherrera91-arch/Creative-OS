"""The vault — where the miner stores the gold it finds.

A :class:`StrategyVault` persists validated strategies (survivors of the honest
lab funnel) to a JSON file, de-duplicated by content hash and kept ranked by
Deflated Sharpe (the honest edge, I9). The best survive; weaker finds are
dropped when the vault is full. It grows across mining runs and restarts, so
you come back to a library of the best strategies found while you were away.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["GoldStrategy", "StrategyVault"]


@dataclass
class GoldStrategy:
    """One strategy the miner judged worth keeping (auditable, I4/I8).

    Attributes:
        spec: the full strategy description (recompilable later).
        spec_hash: content-addressed identity (dedupe key, I8).
        family: strategy family (trend, momentum, mean_reversion, ...).
        name: human-readable strategy name.
        oos_sharpe: out-of-sample Sharpe on the data it was found in.
        deflated_sharpe: honest edge probability after multiple testing (I9).
        regime: the market regime the batch was tested under.
        found_round: mining round it was discovered in.
        source: data it was found on (``"ccxt"`` real or a scenario name).
    """

    spec: dict[str, Any]
    spec_hash: str
    family: str
    name: str
    oos_sharpe: float
    deflated_sharpe: float
    regime: str
    found_round: int
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "spec": self.spec,
            "spec_hash": self.spec_hash,
            "family": self.family,
            "name": self.name,
            "oos_sharpe": self.oos_sharpe,
            "deflated_sharpe": self.deflated_sharpe,
            "regime": self.regime,
            "found_round": self.found_round,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldStrategy:
        """Rebuild from a stored record."""
        return cls(
            spec=data.get("spec", {}),
            spec_hash=str(data["spec_hash"]),
            family=str(data.get("family", "")),
            name=str(data.get("name", "")),
            oos_sharpe=float(data.get("oos_sharpe", 0.0)),
            deflated_sharpe=float(data.get("deflated_sharpe", 0.0)),
            regime=str(data.get("regime", "")),
            found_round=int(data.get("found_round", 0)),
            source=str(data.get("source", "")),
        )


def _rank_key(gold: GoldStrategy) -> tuple[float, float, str]:
    # Best first: highest honest edge, then OOS Sharpe, then stable by hash (I8).
    return (-gold.deflated_sharpe, -gold.oos_sharpe, gold.spec_hash)


class StrategyVault:
    """A persisted, ranked, de-duplicated library of found strategies."""

    def __init__(self, path: str | Path | None = None, max_size: int = 50) -> None:
        """
        Args:
            path: JSON file the vault is stored in; ``~/quantos/vault.json`` by
                default.
            max_size: how many of the best strategies to keep.
        """
        self.path = Path(path) if path else Path.home() / "quantos" / "vault.json"
        self.max_size = max_size

    def all(self) -> list[GoldStrategy]:
        """Every stored strategy, best first."""
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text())
        golds = [GoldStrategy.from_dict(r) for r in raw.get("gold", [])]
        return sorted(golds, key=_rank_key)

    def top(self, n: int | None = None) -> list[GoldStrategy]:
        """The best ``n`` strategies (all of them when ``n`` is None)."""
        golds = self.all()
        return golds if n is None else golds[:n]

    def add(self, finds: list[GoldStrategy]) -> int:
        """Merge new finds in; returns how many were genuinely new (I8 dedupe)."""
        existing = {g.spec_hash: g for g in self.all()}
        added = 0
        for gold in finds:
            if gold.spec_hash not in existing:
                added += 1
            existing[gold.spec_hash] = gold  # newest wins on re-find
        kept = sorted(existing.values(), key=_rank_key)[: self.max_size]
        self._save(kept)
        return added

    def clear(self) -> None:
        """Empty the vault."""
        self.path.unlink(missing_ok=True)

    def __len__(self) -> int:
        return len(self.all())

    def _save(self, golds: list[GoldStrategy]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"gold": [g.as_dict() for g in golds]}
        self.path.write_text(json.dumps(payload, indent=2, default=str))
