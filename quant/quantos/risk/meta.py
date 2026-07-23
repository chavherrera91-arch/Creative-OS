"""Meta-Risk (module 23) — audit the Risk Manager itself, from history.

The Risk Manager guards every decision; Meta-Risk asks *who guards the
guard*. Over the closed archive it measures the veto rate and, crucially,
the **counterfactual quality** of vetoes: when a blocked setup's recorded
outcome (what the intended trade would have returned) is mostly positive, the
limits are over-blocking profitable setups; when *allowed* setups mostly lose,
the limits are too permissive. It also breaks this down per regime, so limits
calibrated for one regime but stale in another are surfaced.

Like every M9 module it **only proposes** — it emits limit-adjustment
proposals and never changes a limit itself (ARCHITECTURE §4.1). Deterministic
over a given archive (I8); reads only recorded outcomes (I4), never the
future (I2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.memory.archive import ArchivedDecision, DecisionArchive

__all__ = ["MetaRisk", "MetaRiskReport", "VetoStats"]


@dataclass
class VetoStats:
    """Veto accounting over a slice of closed decisions.

    Attributes:
        n: closed decisions in the slice.
        n_blocked: how many were vetoed by risk.
        blocked_wins: of the blocked, how many would have won (counterfactual).
        blocked_pnl: summed counterfactual pnl of the blocked setups.
    """

    n: int = 0
    n_blocked: int = 0
    blocked_wins: int = 0
    blocked_pnl: float = 0.0

    @property
    def veto_rate(self) -> float:
        return self.n_blocked / self.n if self.n else 0.0

    @property
    def blocked_win_rate(self) -> float:
        return self.blocked_wins / self.n_blocked if self.n_blocked else 0.0

    @property
    def blocked_mean_pnl(self) -> float:
        return self.blocked_pnl / self.n_blocked if self.n_blocked else 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "n": self.n,
            "n_blocked": self.n_blocked,
            "veto_rate": self.veto_rate,
            "blocked_win_rate": self.blocked_win_rate,
            "blocked_mean_pnl": self.blocked_mean_pnl,
        }


@dataclass
class MetaRiskReport:
    """Meta-Risk's findings + limit-adjustment proposals (I4).

    Attributes:
        overall: veto accounting over the whole closed corpus.
        by_regime: the same, per regime label.
        proposals: suggested (never auto-applied) limit adjustments.
    """

    overall: VetoStats
    by_regime: dict[str, VetoStats] = field(default_factory=dict)
    proposals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def over_blocking(self) -> bool:
        """True when any proposal argues for relaxing the limits."""
        return any(p["kind"] == "relax_limits" for p in self.proposals)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "overall": self.overall.as_dict(),
            "by_regime": {k: v.as_dict() for k, v in self.by_regime.items()},
            "proposals": list(self.proposals),
        }


def _is_blocked(record: ArchivedDecision) -> bool:
    return bool(record.decision.get("blocked_by_risk", False))


class MetaRisk:
    """Audit the Risk Manager from the closed archive; propose adjustments."""

    def __init__(
        self,
        min_samples: int = 3,
        over_block_win_rate: float = 0.6,
        under_block_loss_rate: float = 0.6,
    ) -> None:
        """
        Args:
            min_samples: evidence floor before any proposal is made.
            over_block_win_rate: blocked-setup win rate above which the limits
                are judged to be over-blocking (propose relaxation).
            under_block_loss_rate: allowed-setup loss rate above which the
                limits are judged too permissive (propose tightening).
        """
        self.min_samples = min_samples
        self.over_block_win_rate = over_block_win_rate
        self.under_block_loss_rate = under_block_loss_rate

    def assess(self, archive: DecisionArchive) -> MetaRiskReport:
        """Mine the closed corpus and emit veto stats + proposals (I8)."""
        closed = [r for r in archive.closed() if r.pnl is not None]
        overall = VetoStats()
        by_regime: dict[str, VetoStats] = {}
        allowed_losses = allowed_closed = 0

        for record in closed:
            regime = record.regime_label or "unknown"
            stats = by_regime.setdefault(regime, VetoStats())
            for bucket in (overall, stats):
                bucket.n += 1
            if _is_blocked(record):
                for bucket in (overall, stats):
                    bucket.n_blocked += 1
                    bucket.blocked_pnl += record.pnl  # type: ignore[operator]
                    if record.pnl > 0:  # type: ignore[operator]
                        bucket.blocked_wins += 1
            else:
                allowed_closed += 1
                if record.pnl <= 0:  # type: ignore[operator]
                    allowed_losses += 1

        proposals = self._proposals(overall, by_regime, allowed_closed, allowed_losses)
        return MetaRiskReport(
            overall=overall,
            by_regime=dict(sorted(by_regime.items())),
            proposals=proposals,
        )

    def _proposals(
        self,
        overall: VetoStats,
        by_regime: dict[str, VetoStats],
        allowed_closed: int,
        allowed_losses: int,
    ) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []

        if (
            overall.n_blocked >= self.min_samples
            and overall.blocked_win_rate >= self.over_block_win_rate
            and overall.blocked_mean_pnl > 0
        ):
            proposals.append(
                {
                    "kind": "relax_limits",
                    "scope": "global",
                    "detail": (
                        f"risk vetoed {overall.n_blocked} setups of which "
                        f"{overall.blocked_win_rate:.0%} would have won "
                        f"({overall.blocked_mean_pnl:+.2f} mean counterfactual pnl) — "
                        "propose relaxing the limits"
                    ),
                }
            )

        allowed_loss_rate = allowed_losses / allowed_closed if allowed_closed else 0.0
        if allowed_closed >= self.min_samples and allowed_loss_rate >= self.under_block_loss_rate:
            proposals.append(
                {
                    "kind": "tighten_limits",
                    "scope": "global",
                    "detail": (
                        f"{allowed_loss_rate:.0%} of {allowed_closed} allowed setups lost — "
                        "propose tightening the limits"
                    ),
                }
            )

        for regime, stats in sorted(by_regime.items()):
            if (
                stats.n_blocked >= self.min_samples
                and stats.blocked_win_rate >= self.over_block_win_rate
                and stats.blocked_mean_pnl > 0
            ):
                proposals.append(
                    {
                        "kind": "relax_limits",
                        "scope": "regime",
                        "regime": regime,
                        "detail": (
                            f"in {regime} the limits blocked {stats.n_blocked} setups at a "
                            f"{stats.blocked_win_rate:.0%} counterfactual win rate — limits look "
                            "stale for this regime; propose a regime-specific relaxation"
                        ),
                    }
                )
        return proposals
