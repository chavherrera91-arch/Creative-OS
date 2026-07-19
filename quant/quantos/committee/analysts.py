"""Specialist analysts (ARCHITECTURE §3).

Deterministic, rule-based specialists. The technical and statistical
analysts work from OHLCV; the macro, sentiment and on-chain analysts are
data-hungry and **abstain honestly** when their channel is absent from the
snapshot (invariant I3) — real channel data arrives with the M2 Data Lake.
The :class:`AnomalyAnalyst` (M4) surfaces unusual market conditions as
direction-neutral caution. LLM-backed analysts (M6) will plug into the same
``Analyst`` ABC (I7).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from quantos.anomaly.base import AnomalyDetector, anomaly_summary
from quantos.anomaly.detectors import ZScoreDetector
from quantos.committee.base import Analyst, AnalystOpinion, Direction, Evidence
from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind

__all__ = [
    "MIN_BARS",
    "AnomalyAnalyst",
    "MacroAnalyst",
    "OnChainAnalyst",
    "SentimentAnalyst",
    "StatisticalAnalyst",
    "TechnicalAnalyst",
    "default_analysts",
]

#: Minimum history the OHLCV-driven analysts require before opining.
MIN_BARS = 60


def _clip(value: float) -> float:
    """Clamp a raw score into the legal Evidence impact range."""
    return float(np.clip(value, -1.0, 1.0))


class TechnicalAnalyst(Analyst):
    """Trend and momentum from OHLCV (EMA structure, MACD, RSI, Bollinger)."""

    def __init__(self, name: str = "Technical Analyst") -> None:
        super().__init__(name=name, category="technical")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        if snapshot.bars < MIN_BARS:
            return self._abstain(f"insufficient history ({snapshot.bars} < {MIN_BARS} bars)")
        close = snapshot.ohlcv["close"]
        evidence: list[Evidence] = []

        ema_fast = float(ind.ema(close, 20).iloc[-1])
        ema_slow = float(ind.ema(close, 50).iloc[-1])
        trend_pct = (ema_fast - ema_slow) / ema_slow
        evidence.append(
            Evidence(
                name="ema_trend",
                detail=f"EMA20 is {trend_pct:+.2%} vs EMA50 "
                f"({'up' if trend_pct > 0 else 'down'}trend structure)",
                impact=_clip(trend_pct * 50.0),
                value=trend_pct,
            )
        )

        atr_last = float(ind.atr(snapshot.ohlcv["high"], snapshot.ohlcv["low"], close, 14).iloc[-1])
        hist = float(ind.macd(close)["histogram"].iloc[-1])
        macd_score = hist / atr_last if atr_last > 0 else 0.0
        evidence.append(
            Evidence(
                name="macd_momentum",
                detail=f"MACD histogram is {macd_score:+.2f} ATRs",
                impact=_clip(macd_score),
                value=hist,
            )
        )

        rsi_last = float(ind.rsi(close, 14).iloc[-1])
        evidence.append(
            Evidence(
                name="rsi",
                detail=f"RSI(14) at {rsi_last:.1f}",
                impact=_clip((rsi_last - 50.0) / 50.0) * 0.6,
                value=rsi_last,
            )
        )

        pct_b = float(ind.bollinger(close, 20)["percent_b"].iloc[-1])
        evidence.append(
            Evidence(
                name="bollinger_position",
                detail=f"price sits at {pct_b:.0%} of the Bollinger band",
                impact=_clip((pct_b - 0.5) * 2.0) * 0.4,
                value=pct_b,
            )
        )
        return self._from_evidence(evidence)


class StatisticalAnalyst(Analyst):
    """Mean-reversion / short-horizon statistical edges from OHLCV."""

    def __init__(self, name: str = "Statistical Analyst") -> None:
        super().__init__(name=name, category="statistical")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        if snapshot.bars < MIN_BARS:
            return self._abstain(f"insufficient history ({snapshot.bars} < {MIN_BARS} bars)")
        close = snapshot.ohlcv["close"]
        evidence: list[Evidence] = []

        z = float(ind.zscore(close, 20).iloc[-1])
        evidence.append(
            Evidence(
                name="zscore_reversion",
                detail=f"price is {z:+.2f}σ from its 20-bar mean (reversion pull)",
                impact=_clip(-z / 2.5) * 0.8,
                value=z,
            )
        )

        mom = float(close.pct_change(5).iloc[-1])
        evidence.append(
            Evidence(
                name="short_momentum",
                detail=f"5-bar momentum {mom:+.2%} (continuation)",
                impact=_clip(mom * 20.0) * 0.5,
                value=mom,
            )
        )

        vol = ind.rolling_volatility(close, 20)
        vol_now = float(vol.iloc[-1])
        vol_med = float(vol.median())
        ratio = vol_now / vol_med if vol_med > 0 else 1.0
        evidence.append(
            Evidence(
                name="volatility_regime",
                detail=f"realised vol is {ratio:.2f}x its median (context, direction-neutral)",
                impact=0.0,
                value=ratio,
            )
        )

        # Forward-compat (M5/M7): validated strategy signals feed this analyst.
        if context and "strategy_signal" in context:
            signal = float(context["strategy_signal"])
            evidence.append(
                Evidence(
                    name="strategy_signal",
                    detail="aggregate signal from regime-validated strategies",
                    impact=_clip(signal),
                    value=signal,
                )
            )
        return self._from_evidence(evidence)


class MacroAnalyst(Analyst):
    """Macro backdrop: dollar, rates, risk appetite. Abstains without data (I3)."""

    def __init__(self, name: str = "Macro Analyst") -> None:
        super().__init__(name=name, category="macro")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        macro = snapshot.macro
        if not macro:
            return self._abstain("no macro channel in snapshot")
        evidence: list[Evidence] = []
        if "dxy_trend" in macro:
            dxy = float(macro["dxy_trend"])
            evidence.append(
                Evidence(
                    name="dxy",
                    detail=f"dollar trend {dxy:+.2f} (a rising dollar pressures crypto)",
                    impact=_clip(-dxy),
                    value=dxy,
                )
            )
        if "rates_trend" in macro:
            rates = float(macro["rates_trend"])
            evidence.append(
                Evidence(
                    name="rates",
                    detail=f"rates trend {rates:+.2f} (tightening is a headwind)",
                    impact=_clip(-rates),
                    value=rates,
                )
            )
        if "risk_appetite" in macro:
            risk = float(macro["risk_appetite"])
            evidence.append(
                Evidence(
                    name="risk_appetite",
                    detail=f"cross-asset risk appetite {risk:+.2f}",
                    impact=_clip(risk),
                    value=risk,
                )
            )
        if not evidence:
            return self._abstain("macro channel present but carries no known fields")
        return self._from_evidence(evidence)


class SentimentAnalyst(Analyst):
    """Crowd sentiment; extremes read contrarian. Abstains without data (I3)."""

    def __init__(self, name: str = "Sentiment Analyst") -> None:
        super().__init__(name=name, category="sentiment")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        sentiment = snapshot.sentiment
        if not sentiment or "score" not in sentiment:
            return self._abstain("no sentiment channel in snapshot")
        score = float(sentiment["score"])
        evidence = [
            Evidence(
                name="crowd_sentiment",
                detail=f"aggregate social/news sentiment {score:+.2f}",
                impact=_clip(score),
                value=score,
            )
        ]
        if abs(score) > 0.8:
            evidence.append(
                Evidence(
                    name="sentiment_extreme",
                    detail="sentiment is at a euphoric/capitulation extreme (contrarian risk)",
                    impact=_clip(-0.4 * np.sign(score)),
                    value=score,
                )
            )
        return self._from_evidence(evidence)


class OnChainAnalyst(Analyst):
    """Exchange flows, whales, stablecoins. Abstains without data (I3)."""

    def __init__(self, name: str = "On-chain Analyst") -> None:
        super().__init__(name=name, category="onchain")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        onchain = snapshot.onchain
        if not onchain:
            return self._abstain("no on-chain channel in snapshot")
        evidence: list[Evidence] = []
        if "net_exchange_flow" in onchain:
            flow = float(onchain["net_exchange_flow"])
            evidence.append(
                Evidence(
                    name="exchange_flow",
                    detail=f"net exchange flow {flow:+.0f} (inflows imply sell pressure)",
                    impact=_clip(-flow / 2_000.0),
                    value=flow,
                )
            )
        if "whale_accumulation" in onchain:
            whale = float(onchain["whale_accumulation"])
            evidence.append(
                Evidence(
                    name="whale_accumulation",
                    detail=f"whale accumulation score {whale:+.2f}",
                    impact=_clip(whale),
                    value=whale,
                )
            )
        if "stablecoin_supply_change" in onchain:
            stable = float(onchain["stablecoin_supply_change"])
            evidence.append(
                Evidence(
                    name="stablecoin_supply",
                    detail=f"stablecoin supply change {stable:+.2%} (dry powder)",
                    impact=_clip(stable * 20.0),
                    value=stable,
                )
            )
        if not evidence:
            return self._abstain("on-chain channel present but carries no known fields")
        return self._from_evidence(evidence)


class AnomalyAnalyst(Analyst):
    """Unusual market conditions as explicit, direction-neutral caution (M4).

    Reads the anomaly summary from the deliberation context (``anomalies``,
    injected by the orchestrator per ARCHITECTURE §4) or computes it from the
    snapshot with its own dependency-free detector. With **no active anomaly
    it abstains honestly** (I3) — silence carries no conviction. With an
    active anomaly it emits a FLAT stance whose confidence scales with
    severity: the evidence is direction-neutral (an anomaly says "trust this
    tape less", not "short it"), so in aggregation it dampens the composite
    conviction rather than picking a side.
    """

    def __init__(
        self, name: str = "Anomaly Analyst", detector: AnomalyDetector | None = None
    ) -> None:
        super().__init__(name=name, category="anomaly")
        self.detector: AnomalyDetector = detector or ZScoreDetector()

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        summary = (context or {}).get("anomalies")
        if not isinstance(summary, dict):
            if snapshot.bars < MIN_BARS:
                return self._abstain(f"insufficient history ({snapshot.bars} < {MIN_BARS} bars)")
            summary = anomaly_summary(self.detector, snapshot.ohlcv)
        if not summary.get("active"):
            return self._abstain("no active anomalies at the last bar")

        threshold = float(summary.get("threshold", 1.0)) or 1.0
        kinds: dict[str, Any] = summary.get("kinds") or {}
        evidence = [
            Evidence(
                name=f"anomaly_{kind}",
                detail=(
                    f"{kind.replace('_', ' ')} at {float(report['score']):.1f} "
                    f"(threshold {threshold:.1f}) — direction-neutral caution"
                ),
                impact=0.0,
                value=float(report["score"]),
            )
            for kind, report in sorted(kinds.items())
            if report.get("flag")
        ]
        if not evidence:
            evidence = [
                Evidence(
                    name="anomaly_composite",
                    detail=f"composite anomaly score {float(summary.get('score', 0.0)):.1f} "
                    f"(threshold {threshold:.1f}) — direction-neutral caution",
                    impact=0.0,
                    value=float(summary.get("score", 0.0)),
                )
            ]
        severity = min(1.0, float(summary.get("score", 0.0)) / (2.0 * threshold))
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.FLAT,
            confidence=severity,
            evidence=evidence,
        )


def default_analysts() -> list[Analyst]:
    """The default M1 committee bench."""
    return [
        TechnicalAnalyst(),
        StatisticalAnalyst(),
        MacroAnalyst(),
        SentimentAnalyst(),
        OnChainAnalyst(),
    ]
