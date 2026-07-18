"""Composable risk limit library (module 8, M3 scope).

Each rule is a small, independently-testable object with a single
``check(snapshot, report, context) -> RiskCheck`` method returning ``ok``,
``warning`` or ``veto``. The :class:`~quantos.committee.risk_manager.RiskManager`
runs a configurable list of these rules; **a single veto is absolute**
(invariant I5). :func:`default_rules` reproduces the exact M1 behaviour, so the
refactor is back-compatible by construction.

Rules read only the snapshot and the deliberation context — never the future
(I2) — and are pure functions of their inputs (I8).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from quantos.committee.confidence import ConfidenceReport

__all__ = [
    "OK",
    "VETO",
    "WARNING",
    "CorrelationBreak",
    "DailyDrawdown",
    "LowLiquidity",
    "MacroEvent",
    "MaxPositionSize",
    "RiskCheck",
    "RiskRule",
    "VolatilitySpike",
    "default_rules",
]

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


class RiskRule(ABC):
    """One composable risk rule.

    Subclasses set :attr:`name` and implement :meth:`check`. Helper
    constructors (:meth:`ok`, :meth:`warning`, :meth:`veto`) keep the rule
    bodies terse and the check names consistent.
    """

    name: str = "risk_rule"

    @abstractmethod
    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        """Evaluate the rule against a snapshot (and optional context)."""

    def ok(self, message: str, value: float | None = None) -> RiskCheck:
        """A passing check."""
        return RiskCheck(self.name, OK, message, value)

    def warning(self, message: str, value: float | None = None) -> RiskCheck:
        """A non-blocking warning."""
        return RiskCheck(self.name, WARNING, message, value)

    def veto(self, message: str, value: float | None = None) -> RiskCheck:
        """An absolute veto (I5)."""
        return RiskCheck(self.name, VETO, message, value)


class VolatilitySpike(RiskRule):
    """Veto when realised volatility spikes far above its own median."""

    name = "volatility_spike"

    def __init__(
        self, max_ratio: float = 2.5, warn_ratio: float = 1.8, window: int = 20
    ) -> None:
        """
        Args:
            max_ratio: veto when current realised vol exceeds this multiple of
                its sample median.
            warn_ratio: warning level for the same ratio.
            window: rolling window for realised volatility.
        """
        self.max_ratio = max_ratio
        self.warn_ratio = warn_ratio
        self.window = window

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        close = snapshot.ohlcv["close"]
        vol = ind.rolling_volatility(close, self.window)
        vol_now, vol_med = float(vol.iloc[-1]), float(vol.median())
        if vol_med <= 0 or vol.isna().all():
            return self.ok("not enough history to judge volatility")
        ratio = vol_now / vol_med
        message = f"realised vol is {ratio:.2f}x its median"
        if ratio >= self.max_ratio:
            return self.veto(f"volatility spike: {message}", ratio)
        if ratio >= self.warn_ratio:
            return self.warning(f"elevated volatility: {message}", ratio)
        return self.ok(message, ratio)


class MacroEvent(RiskRule):
    """Veto around high-impact macro events; warn on medium-impact ones."""

    name = "macro_event"

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        events = list(snapshot.events or [])
        if context and context.get("macro_event"):
            events.append({"name": str(context["macro_event"]), "impact": "high"})
        high = [e for e in events if str(e.get("impact", "")).lower() == "high"]
        medium = [e for e in events if str(e.get("impact", "")).lower() == "medium"]
        if high:
            names = ", ".join(str(e.get("name", "?")) for e in high)
            return self.veto(f"high-impact macro event imminent: {names}", float(len(high)))
        if medium:
            names = ", ".join(str(e.get("name", "?")) for e in medium)
            return self.warning(f"medium-impact event on calendar: {names}", float(len(medium)))
        return self.ok("no high-impact events on the calendar", 0.0)


class DailyDrawdown(RiskRule):
    """Veto when the day's portfolio loss breaches the drawdown limit."""

    name = "daily_drawdown"

    def __init__(self, max_daily_drawdown: float = 0.05) -> None:
        """
        Args:
            max_daily_drawdown: veto when context ``daily_pnl_pct`` is at or
                below ``-max_daily_drawdown``.
        """
        self.max_daily_drawdown = max_daily_drawdown

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        pnl = float((context or {}).get("daily_pnl_pct", 0.0))
        if pnl <= -self.max_daily_drawdown:
            return self.veto(
                f"daily loss {pnl:.1%} breaches the {self.max_daily_drawdown:.0%} limit", pnl
            )
        return self.ok(f"daily P&L {pnl:+.1%} within limits", pnl)


class LowLiquidity(RiskRule):
    """Veto when recent volume collapses versus its own median."""

    name = "low_liquidity"

    def __init__(
        self, min_ratio: float = 0.3, warn_ratio: float = 0.6, window: int = 20
    ) -> None:
        """
        Args:
            min_ratio: veto when recent volume falls to or below this fraction
                of its sample median.
            warn_ratio: warning level for the same ratio.
            window: rolling window for recent volume.
        """
        self.min_ratio = min_ratio
        self.warn_ratio = warn_ratio
        self.window = window

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        volume = snapshot.ohlcv["volume"]
        recent = float(volume.tail(self.window).mean())
        median = float(volume.median())
        if median <= 0:
            return self.veto("no measurable volume", 0.0)
        ratio = recent / median
        message = f"recent volume is {ratio:.2f}x its median"
        if ratio <= self.min_ratio:
            return self.veto(f"liquidity collapse: {message}", ratio)
        if ratio <= self.warn_ratio:
            return self.warning(f"thin liquidity: {message}", ratio)
        return self.ok(message, ratio)


class CorrelationBreak(RiskRule):
    """Veto when the asset's correlation to its benchmark breaks down.

    A structural break in a normally-stable correlation (e.g. BTC decoupling
    from the broad market) signals an abnormal market where historical
    validation no longer applies. The benchmark close series arrives through
    the deliberation context under ``benchmark_close`` (aligned or alignable
    to the snapshot's index); without a benchmark the rule passes — it never
    fabricates a reading (I3 in spirit).
    """

    name = "correlation_break"

    def __init__(
        self, max_break: float = 0.6, warn_break: float = 0.35, window: int = 20
    ) -> None:
        """
        Args:
            max_break: veto when full-sample minus recent correlation exceeds
                this drop.
            warn_break: warning level for the same drop.
            window: recent window for the short-horizon correlation.
        """
        self.max_break = max_break
        self.warn_break = warn_break
        self.window = window

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        benchmark = (context or {}).get("benchmark_close")
        if benchmark is None:
            return self.ok("no benchmark supplied — correlation not assessed")
        close = snapshot.ohlcv["close"].astype(float)
        bench = pd.Series(benchmark).reindex(close.index).astype(float)
        asset_ret = close.pct_change()
        bench_ret = bench.pct_change()
        if len(close) < 2 * self.window or bench_ret.dropna().empty:
            return self.ok("not enough overlapping history to judge correlation")
        full = float(asset_ret.corr(bench_ret))
        recent = float(asset_ret.tail(self.window).corr(bench_ret.tail(self.window)))
        if pd.isna(full) or pd.isna(recent):
            return self.ok("correlation undefined on this sample")
        drop = full - recent
        message = f"correlation {full:+.2f} full-sample vs {recent:+.2f} recent"
        if drop >= self.max_break:
            return self.veto(f"correlation break: {message}", drop)
        if drop >= self.warn_break:
            return self.warning(f"correlation weakening: {message}", drop)
        return self.ok(message, drop)


class MaxPositionSize(RiskRule):
    """Veto any order that would exceed the maximum position fraction.

    The proposed size arrives through the context under
    ``proposed_position_fraction`` (fraction of equity, absolute). The sizing
    layer (module 26) must consult :attr:`max_fraction` so it can never breach
    this limit (I5); this rule is the backstop should anything try.
    """

    name = "max_position_size"

    def __init__(self, max_fraction: float = 0.25) -> None:
        """
        Args:
            max_fraction: hard cap on a position as a fraction of equity.
        """
        self.max_fraction = max_fraction

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        proposed = (context or {}).get("proposed_position_fraction")
        if proposed is None:
            return self.ok(f"no proposed size — cap is {self.max_fraction:.0%} of equity")
        fraction = abs(float(proposed))
        if fraction > self.max_fraction:
            return self.veto(
                f"proposed position {fraction:.0%} of equity exceeds the "
                f"{self.max_fraction:.0%} cap",
                fraction,
            )
        return self.ok(
            f"proposed position {fraction:.0%} within the {self.max_fraction:.0%} cap", fraction
        )


def default_rules(
    max_vol_ratio: float = 2.5,
    warn_vol_ratio: float = 1.8,
    max_daily_drawdown: float = 0.05,
    min_volume_ratio: float = 0.3,
    warn_volume_ratio: float = 0.6,
    vol_window: int = 20,
) -> list[RiskRule]:
    """The M1-equivalent rule set, in the M1 order (back-compatible).

    ``CorrelationBreak`` and ``MaxPositionSize`` are additive opt-ins: they are
    not part of the default set so existing behaviour (and its tests) is
    preserved bit-for-bit.
    """
    return [
        VolatilitySpike(max_ratio=max_vol_ratio, warn_ratio=warn_vol_ratio, window=vol_window),
        MacroEvent(),
        DailyDrawdown(max_daily_drawdown=max_daily_drawdown),
        LowLiquidity(
            min_ratio=min_volume_ratio, warn_ratio=warn_volume_ratio, window=vol_window
        ),
    ]
