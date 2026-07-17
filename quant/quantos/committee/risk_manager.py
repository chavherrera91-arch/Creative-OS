"""The Risk Manager (module 8, M1 scope).

Screens every prospective trade with deterministic rules. Each rule returns a
:class:`RiskCheck` at level ``ok``, ``warning`` or ``veto``. **A single veto is
absolute**: the Chair must stand the committee down regardless of confidence
(invariant I5). The composable rule library arrives in M3 (``risk.limits``);
the constructor/behaviour here stays back-compatible with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.committee.confidence import ConfidenceReport
from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind

__all__ = ["RiskAssessment", "RiskCheck", "RiskManager"]

OK = "ok"
WARNING = "warning"
VETO = "veto"


@dataclass(frozen=True)
class RiskCheck:
    """Outcome of one risk rule."""

    name: str
    level: str  # ok | warning | veto
    message: str
    value: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "name": self.name,
            "level": self.level,
            "message": self.message,
            "value": self.value,
        }


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
    """Deterministic rule screen: volatility, macro events, drawdown, liquidity."""

    def __init__(
        self,
        max_vol_ratio: float = 2.5,
        warn_vol_ratio: float = 1.8,
        max_daily_drawdown: float = 0.05,
        min_volume_ratio: float = 0.3,
        warn_volume_ratio: float = 0.6,
        vol_window: int = 20,
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
        """
        self.max_vol_ratio = max_vol_ratio
        self.warn_vol_ratio = warn_vol_ratio
        self.max_daily_drawdown = max_daily_drawdown
        self.min_volume_ratio = min_volume_ratio
        self.warn_volume_ratio = warn_volume_ratio
        self.vol_window = vol_window

    # -- individual rules ---------------------------------------------------

    def _check_volatility(self, snapshot: MarketSnapshot) -> RiskCheck:
        close = snapshot.ohlcv["close"]
        vol = ind.rolling_volatility(close, self.vol_window)
        vol_now, vol_med = float(vol.iloc[-1]), float(vol.median())
        if vol_med <= 0 or vol.isna().all():
            return RiskCheck("volatility_spike", OK, "not enough history to judge volatility")
        ratio = vol_now / vol_med
        message = f"realised vol is {ratio:.2f}x its median"
        if ratio >= self.max_vol_ratio:
            return RiskCheck("volatility_spike", VETO, f"volatility spike: {message}", ratio)
        if ratio >= self.warn_vol_ratio:
            return RiskCheck("volatility_spike", WARNING, f"elevated volatility: {message}", ratio)
        return RiskCheck("volatility_spike", OK, message, ratio)

    def _check_macro_event(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None
    ) -> RiskCheck:
        events = list(snapshot.events or [])
        if context and context.get("macro_event"):
            events.append({"name": str(context["macro_event"]), "impact": "high"})
        high = [e for e in events if str(e.get("impact", "")).lower() == "high"]
        medium = [e for e in events if str(e.get("impact", "")).lower() == "medium"]
        if high:
            names = ", ".join(str(e.get("name", "?")) for e in high)
            return RiskCheck(
                "macro_event", VETO, f"high-impact macro event imminent: {names}", float(len(high))
            )
        if medium:
            names = ", ".join(str(e.get("name", "?")) for e in medium)
            return RiskCheck(
                "macro_event",
                WARNING,
                f"medium-impact event on calendar: {names}",
                float(len(medium)),
            )
        return RiskCheck("macro_event", OK, "no high-impact events on the calendar", 0.0)

    def _check_daily_drawdown(self, context: dict[str, Any] | None) -> RiskCheck:
        pnl = float((context or {}).get("daily_pnl_pct", 0.0))
        if pnl <= -self.max_daily_drawdown:
            return RiskCheck(
                "daily_drawdown",
                VETO,
                f"daily loss {pnl:.1%} breaches the {self.max_daily_drawdown:.0%} limit",
                pnl,
            )
        return RiskCheck("daily_drawdown", OK, f"daily P&L {pnl:+.1%} within limits", pnl)

    def _check_liquidity(self, snapshot: MarketSnapshot) -> RiskCheck:
        volume = snapshot.ohlcv["volume"]
        recent = float(volume.tail(self.vol_window).mean())
        median = float(volume.median())
        if median <= 0:
            return RiskCheck("low_liquidity", VETO, "no measurable volume", 0.0)
        ratio = recent / median
        message = f"recent volume is {ratio:.2f}x its median"
        if ratio <= self.min_volume_ratio:
            return RiskCheck("low_liquidity", VETO, f"liquidity collapse: {message}", ratio)
        if ratio <= self.warn_volume_ratio:
            return RiskCheck("low_liquidity", WARNING, f"thin liquidity: {message}", ratio)
        return RiskCheck("low_liquidity", OK, message, ratio)

    # -- assessment ---------------------------------------------------------

    def assess(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        """Run every rule and consolidate into a :class:`RiskAssessment`.

        The ``report`` parameter is accepted for signature stability (rules that
        depend on the committee's conviction arrive with M3).
        """
        checks = [
            self._check_volatility(snapshot),
            self._check_macro_event(snapshot, context),
            self._check_daily_drawdown(context),
            self._check_liquidity(snapshot),
        ]
        vetoes = [c.message for c in checks if c.level == VETO]
        warnings = [c.message for c in checks if c.level == WARNING]
        return RiskAssessment(vetoed=bool(vetoes), vetoes=vetoes, warnings=warnings, checks=checks)
