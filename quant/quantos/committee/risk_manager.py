"""The Risk Manager (module 8).

Screens every prospective trade by running a configurable list of composable
:class:`~quantos.risk.limits.RiskRule` objects (M3, ``quantos.risk.limits``).
Each rule returns a :class:`RiskCheck` at level ``ok``, ``warning`` or
``veto``. **A single veto is absolute**: the Chair must stand the committee
down regardless of confidence (invariant I5).

The constructor keeps its M1 signature and default behaviour: with no explicit
``rules``, :func:`~quantos.risk.limits.default_rules` builds the original four
rules (volatility spike, macro event, daily drawdown, low liquidity) from the
same parameters — back-compatible by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from quantos.committee.confidence import ConfidenceReport
from quantos.data.models import MarketSnapshot
from quantos.risk.limits import OK, VETO, WARNING, RiskCheck, RiskRule, default_rules

__all__ = ["OK", "VETO", "WARNING", "RiskAssessment", "RiskCheck", "RiskManager"]


@dataclass
class RiskAssessment:
    """The Risk Manager's verdict over all rules.

    Attributes:
        vetoed: True when any rule vetoed — absolute (I5).
        vetoes: messages of vetoing rules.
        warnings: messages of warning rules.
        checks: every rule outcome, including passes (auditable, I4).
    """

    vetoed: bool
    vetoes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[RiskCheck] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        """Convenience inverse of ``vetoed``."""
        return not self.vetoed

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "vetoed": self.vetoed,
            "vetoes": list(self.vetoes),
            "warnings": list(self.warnings),
            "checks": [c.as_dict() for c in self.checks],
        }


class RiskManager:
    """Deterministic rule screen over a configurable, composable rule list."""

    def __init__(
        self,
        max_vol_ratio: float = 2.5,
        warn_vol_ratio: float = 1.8,
        max_daily_drawdown: float = 0.05,
        min_volume_ratio: float = 0.3,
        warn_volume_ratio: float = 0.6,
        vol_window: int = 20,
        rules: Sequence[RiskRule] | None = None,
    ) -> None:
        """
        Args:
            max_vol_ratio: veto when current realised vol exceeds this multiple
                of its sample median (volatility spike).
            warn_vol_ratio: warning level for the same ratio.
            max_daily_drawdown: veto when the day's portfolio P&L (from
                context ``daily_pnl_pct``) is at or below ``-max_daily_drawdown``.
            min_volume_ratio: veto when recent volume falls to or below this
                fraction of its sample median (low liquidity).
            warn_volume_ratio: warning level for the same ratio.
            vol_window: rolling window for realised volatility and volume.
            rules: explicit rule list; when omitted, the M1-equivalent default
                set is built from the parameters above (back-compatible).
        """
        self.max_vol_ratio = max_vol_ratio
        self.warn_vol_ratio = warn_vol_ratio
        self.max_daily_drawdown = max_daily_drawdown
        self.min_volume_ratio = min_volume_ratio
        self.warn_volume_ratio = warn_volume_ratio
        self.vol_window = vol_window
        self.rules: list[RiskRule] = (
            list(rules)
            if rules is not None
            else default_rules(
                max_vol_ratio=max_vol_ratio,
                warn_vol_ratio=warn_vol_ratio,
                max_daily_drawdown=max_daily_drawdown,
                min_volume_ratio=min_volume_ratio,
                warn_volume_ratio=warn_volume_ratio,
                vol_window=vol_window,
            )
        )

    def assess(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        """Run every configured rule and consolidate into a :class:`RiskAssessment`.

        Args:
            snapshot: the market view under assessment.
            report: the committee's aggregated conviction (available to rules
                that condition on it).
            context: deliberation context (``daily_pnl_pct``, ``macro_event``,
                ``benchmark_close``, ``proposed_position_fraction``, ...).

        Returns:
            The consolidated assessment; ``vetoed`` is True on any single
            veto (I5).
        """
        checks = [rule.check(snapshot, report, context) for rule in self.rules]
        vetoes = [c.message for c in checks if c.level == VETO]
        warnings = [c.message for c in checks if c.level == WARNING]
        return RiskAssessment(vetoed=bool(vetoes), vetoes=vetoes, warnings=warnings, checks=checks)
