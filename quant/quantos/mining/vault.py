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
    markets: tuple[str, ...] = ()

    @property
    def diamond(self) -> bool:
        """A 'diamond' 💎: it passed in **two or more markets** (cross-market edge)."""
        return len(self.markets) >= 2

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
            "markets": list(self.markets),
            "diamond": self.diamond,
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
            markets=tuple(data.get("markets", ())),
        )


def _rank_key(gold: GoldStrategy) -> tuple[int, float, float, str]:
    # Diamonds first (cross-market), then honest edge, then OOS, then hash (I8).
    return (0 if gold.diamond else 1, -gold.deflated_sharpe, -gold.oos_sharpe, gold.spec_hash)


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
        """Merge new finds in; returns how many were genuinely new (I8 dedupe).

        Re-finding a strategy in a **new market** unions its markets — that is
        how a single-market find grows into a cross-market 💎 diamond over time.
        """
        existing = {g.spec_hash: g for g in self.all()}
        added = 0
        for gold in finds:
            prev = existing.get(gold.spec_hash)
            if prev is None:
                added += 1
                existing[gold.spec_hash] = gold
            else:
                existing[gold.spec_hash] = GoldStrategy(
                    spec=gold.spec or prev.spec,
                    spec_hash=gold.spec_hash,
                    family=gold.family or prev.family,
                    name=gold.name or prev.name,
                    oos_sharpe=max(gold.oos_sharpe, prev.oos_sharpe),
                    deflated_sharpe=max(gold.deflated_sharpe, prev.deflated_sharpe),
                    regime=gold.regime or prev.regime,
                    found_round=prev.found_round,
                    source=prev.source or gold.source,
                    markets=tuple(sorted(set(prev.markets) | set(gold.markets))),
                )
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
