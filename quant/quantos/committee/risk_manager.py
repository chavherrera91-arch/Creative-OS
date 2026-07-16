"""Risk Manager.

The one member of the committee that can say *NO*. It does not vote on direction;
it screens the proposed trade against hard limits and returns vetoes (blocking)
and warnings (non-blocking). A single veto blocks the trade regardless of how
bullish everyone else is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.config import RiskConfig
from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind


@dataclass
class RiskAssessment:
    approved: bool
    vetoes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "vetoes": list(self.vetoes),
            "warnings": list(self.warnings),
            "metrics": {k: round(v, 5) for k, v in self.metrics.items()},
        }


class RiskManager:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def assess(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> RiskAssessment:
        context = context or {}
        vetoes: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, float] = {}

        close = snapshot.close

        # 1) Volatility spike: ATR z-score against its own recent history.
        if len(close) > 60:
            atr = ind.atr(snapshot.ohlcv, 14)
            atr_pct = (atr / close).dropna()
            if len(atr_pct) > 30 and atr_pct.std() > 0:
                z = float((atr_pct.iloc[-1] - atr_pct.mean()) / atr_pct.std())
                metrics["atr_zscore"] = z
                if z >= self.config.vol_zscore_veto:
                    vetoes.append(
                        f"Volatility spike: ATR z-score {z:.2f} >= {self.config.vol_zscore_veto}"
                    )
                elif z >= self.config.vol_zscore_veto * 0.7:
                    warnings.append(f"Elevated volatility (ATR z-score {z:.2f})")

        # 2) Imminent macro event (FOMC / NFP / CPI) flagged in context/snapshot.
        events = {**snapshot.events, **context.get("events", {})}
        for name, active in events.items():
            if active:
                vetoes.append(f"Imminent macro event: {name}")

        # 3) Daily drawdown breach from portfolio context.
        dd = context.get("daily_drawdown")
        if dd is not None:
            metrics["daily_drawdown"] = float(dd)
            if abs(float(dd)) >= self.config.max_daily_drawdown:
                vetoes.append(
                    f"Daily drawdown {float(dd):.2%} >= limit {self.config.max_daily_drawdown:.2%}"
                )

        # 4) Low liquidity: current volume vs recent median.
        vol = snapshot.ohlcv["volume"]
        if len(vol) > 30:
            median_vol = float(vol.tail(30).median())
            if median_vol > 0:
                ratio = float(vol.iloc[-1]) / median_vol
                metrics["liquidity_ratio"] = ratio
                if ratio < self.config.min_liquidity_ratio:
                    vetoes.append(
                        f"Low liquidity: volume {ratio:.2f}x median < {self.config.min_liquidity_ratio}"
                    )

        return RiskAssessment(
            approved=not vetoes,
            vetoes=vetoes,
            warnings=warnings,
            metrics=metrics,
        )
