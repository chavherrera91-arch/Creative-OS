"""Portfolio Intelligence (module 22) — the whole-book view feeding risk.

The :class:`PortfolioAnalyzer` looks across the book at once: cross-asset
correlations, net/gross and per-cluster exposures, and concentration. Its
:class:`PortfolioReport` is a plain record (I4) the dashboard renders and the
Risk Manager reads. :class:`PortfolioConcentration` is a drop-in
:class:`~quantos.risk.limits.RiskRule` (I7) that turns a concentrated book
into a warning or an absolute veto (I5) — the "flag consumed by risk" the
milestone calls for. Everything is point-in-time (I2) and deterministic (I8).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

from quantos.data.models import MarketSnapshot
from quantos.portfolio.analytics import (
    Exposure,
    concentration,
    correlation_matrix,
    exposure,
    group_exposures,
)
from quantos.risk.limits import RiskCheck, RiskRule

if TYPE_CHECKING:  # pragma: no cover - typing only
    from quantos.committee.confidence import ConfidenceReport

__all__ = ["PortfolioAnalyzer", "PortfolioConcentration", "PortfolioReport"]

#: A default asset → cluster map for the platform's core universe.
DEFAULT_CLUSTERS: dict[str, str] = {
    "BTC/USDT": "crypto",
    "ETH/USDT": "crypto",
    "BTC": "crypto",
    "ETH": "crypto",
    "NASDAQ": "equity",
    "SPX": "equity",
    "GOLD": "metal",
    "USD": "fx",
    "DXY": "fx",
}


@dataclass
class PortfolioReport:
    """The whole-book snapshot (I4).

    Attributes:
        exposure: net/gross/long/short over the book.
        clusters: exposure per cluster/factor.
        concentration: Herfindahl / largest-weight summary.
        correlations: cross-asset return-correlation matrix.
        flags: raised concentration/correlation flags (risk consumes these).
    """

    exposure: Exposure
    clusters: dict[str, Exposure] = field(default_factory=dict)
    concentration: dict[str, Any] = field(default_factory=dict)
    correlations: pd.DataFrame = field(default_factory=pd.DataFrame)
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (correlations as nested dicts)."""
        return {
            "exposure": self.exposure.as_dict(),
            "clusters": {g: e.as_dict() for g, e in self.clusters.items()},
            "concentration": self.concentration,
            "correlations": self.correlations.round(6).to_dict(),
            "flags": list(self.flags),
        }


class PortfolioAnalyzer:
    """Analyse the book across assets: correlation, exposure, concentration."""

    def __init__(
        self,
        clusters: Mapping[str, str] | None = None,
        max_asset_weight: float = 0.5,
        max_cluster_gross: float = 0.8,
        high_correlation: float = 0.8,
    ) -> None:
        """
        Args:
            clusters: asset → cluster map; :data:`DEFAULT_CLUSTERS` when omitted.
            max_asset_weight: gross weight above which a name is "concentrated".
            max_cluster_gross: cluster gross above which a cluster is flagged.
            high_correlation: |corr| above which two held names are flagged as
                crowding the same bet.
        """
        self.clusters = dict(clusters or DEFAULT_CLUSTERS)
        self.max_asset_weight = max_asset_weight
        self.max_cluster_gross = max_cluster_gross
        self.high_correlation = high_correlation

    def analyze(
        self,
        positions: Mapping[str, float],
        prices: pd.DataFrame | None = None,
        window: int | None = None,
    ) -> PortfolioReport:
        """Build the report from signed positions and (optionally) price history."""
        book = exposure(positions)
        clusters = group_exposures(positions, self.clusters)
        conc = concentration(positions)
        corr = (
            correlation_matrix(prices, window=window)
            if prices is not None and not prices.empty
            else pd.DataFrame()
        )
        flags = self._flags(positions, clusters, conc, corr)
        return PortfolioReport(
            exposure=book,
            clusters=clusters,
            concentration=conc,
            correlations=corr,
            flags=flags,
        )

    def _flags(
        self,
        positions: Mapping[str, float],
        clusters: dict[str, Exposure],
        conc: dict[str, Any],
        corr: pd.DataFrame,
    ) -> list[str]:
        flags: list[str] = []
        if conc["max_weight"] > self.max_asset_weight and conc["max_asset"] is not None:
            flags.append(
                f"concentration: {conc['max_asset']} is {conc['max_weight']:.0%} of gross "
                f"(> {self.max_asset_weight:.0%})"
            )
        for group, exp in clusters.items():
            if exp.gross > self.max_cluster_gross:
                flags.append(
                    f"cluster '{group}' gross {exp.gross:.2f} exceeds {self.max_cluster_gross:.2f}"
                )
        held = [a for a, w in positions.items() if w != 0 and a in getattr(corr, "columns", [])]
        for i, a in enumerate(held):
            for b in held[i + 1 :]:
                rho = float(corr.loc[a, b])
                if abs(rho) >= self.high_correlation:
                    flags.append(
                        f"crowding: {a} and {b} are {rho:+.2f} correlated — one effective bet"
                    )
        return flags


class PortfolioConcentration(RiskRule):
    """Veto/warn on a concentrated book (module 22 flag consumed by risk, I5).

    The analyzer's concentration summary arrives through the deliberation
    context under ``portfolio_concentration`` (or a whole ``portfolio`` report
    dict). Without it the rule passes — it never fabricates a reading (I3).
    """

    name = "portfolio_concentration"

    def __init__(self, max_weight: float = 0.6, warn_weight: float = 0.45) -> None:
        """
        Args:
            max_weight: veto when the largest gross weight is at/above this.
            warn_weight: warning level for the same weight.
        """
        self.max_weight = max_weight
        self.warn_weight = warn_weight

    def check(
        self,
        snapshot: MarketSnapshot,
        report: ConfidenceReport | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskCheck:
        ctx = context or {}
        conc = ctx.get("portfolio_concentration")
        if conc is None and isinstance(ctx.get("portfolio"), dict):
            conc = ctx["portfolio"].get("concentration")
        if not conc:
            return self.ok("no portfolio snapshot supplied — concentration not assessed")
        weight = float(conc.get("max_weight", 0.0))
        asset = conc.get("max_asset")
        message = f"{asset} is {weight:.0%} of gross book"
        if weight >= self.max_weight:
            return self.veto(f"portfolio too concentrated: {message}", weight)
        if weight >= self.warn_weight:
            return self.warning(f"portfolio concentration building: {message}", weight)
        return self.ok(message, weight)
