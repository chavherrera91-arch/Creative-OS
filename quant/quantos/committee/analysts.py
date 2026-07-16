"""Specialist analysts.

Each analyst turns a snapshot into an :class:`AnalystOpinion` with explicit
evidence. The technical analyst always works from OHLCV; the macro / sentiment /
on-chain analysts read their side-channel from the snapshot and *abstain*
honestly when that data is absent (research-first: no fabricated conviction).

Every analyst exposes the same interface, so an LLM-backed analyst can be dropped
in later without changing the committee.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from quantos.committee.base import Analyst, AnalystOpinion, Direction, Evidence
from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


class TechnicalAnalyst(Analyst):
    name = "Technical Analyst"
    category = "technical"

    def __init__(self, fast: int = 20, slow: int = 50, rsi_period: int = 14) -> None:
        self.fast, self.slow, self.rsi_period = fast, slow, rsi_period

    def analyze(self, snapshot: MarketSnapshot, context=None) -> AnalystOpinion:
        close = snapshot.close
        if len(close) < self.slow + 2:
            return self._abstain("insufficient history for moving averages")

        ema_fast = ind.ema(close, self.fast).iloc[-1]
        ema_slow = ind.ema(close, self.slow).iloc[-1]
        rsi = ind.rsi(close, self.rsi_period).iloc[-1]
        macd = ind.macd(close)
        hist = macd["hist"].iloc[-1]

        evidence: list[Evidence] = []
        score = 0.0

        # Trend via EMA relationship (normalised by price).
        trend = (ema_fast - ema_slow) / close.iloc[-1]
        trend_impact = float(np.tanh(trend * 100))
        score += 0.5 * trend_impact
        evidence.append(
            Evidence(
                "ema_cross",
                f"EMA{self.fast} {'>' if ema_fast > ema_slow else '<'} EMA{self.slow}",
                trend_impact,
                round(float(trend), 5),
            )
        )

        # Momentum via MACD histogram sign/magnitude.
        macd_impact = float(np.tanh(hist / close.iloc[-1] * 200))
        score += 0.3 * macd_impact
        evidence.append(
            Evidence("macd_hist", f"MACD histogram {hist:+.4f}", macd_impact, round(float(hist), 5))
        )

        # RSI: distance from 50, penalising overbought/oversold extremes.
        rsi_impact = float((rsi - 50) / 50)
        if rsi > 70:
            rsi_impact *= 0.3  # overbought — fade the long conviction
        elif rsi < 30:
            rsi_impact *= 0.3
        score += 0.2 * rsi_impact
        evidence.append(Evidence("rsi", f"RSI(14) = {rsi:.1f}", 0.2 * rsi_impact, round(float(rsi), 2)))

        direction = Direction.LONG if score > 0 else Direction.SHORT if score < 0 else Direction.FLAT
        return self._opinion(direction, _clip01(abs(score)), evidence)


class MacroAnalyst(Analyst):
    """Reads the ``macro`` side-channel (DXY trend, rate bias, risk regime)."""

    name = "Macro Analyst"
    category = "macro"

    def analyze(self, snapshot: MarketSnapshot, context=None) -> AnalystOpinion:
        macro = snapshot.macro or {}
        if not macro:
            return self._abstain("no macro data supplied")

        evidence: list[Evidence] = []
        score = 0.0
        # dxy_trend: positive DXY generally headwind for risk assets.
        if "dxy_trend" in macro:
            impact = -float(np.tanh(macro["dxy_trend"]))
            score += 0.5 * impact
            evidence.append(Evidence("dxy", f"DXY trend {macro['dxy_trend']:+.2f}", 0.5 * impact))
        # rate_bias: +1 hawkish (headwind), -1 dovish (tailwind).
        if "rate_bias" in macro:
            impact = -float(np.tanh(macro["rate_bias"]))
            score += 0.3 * impact
            evidence.append(Evidence("rates", f"Rate bias {macro['rate_bias']:+.2f}", 0.3 * impact))
        # risk_on: +1 risk-on, -1 risk-off.
        if "risk_on" in macro:
            impact = float(np.tanh(macro["risk_on"]))
            score += 0.2 * impact
            evidence.append(Evidence("risk_regime", f"Risk-on {macro['risk_on']:+.2f}", 0.2 * impact))

        if not evidence:
            return self._abstain("macro channel present but empty")
        direction = Direction.LONG if score > 0 else Direction.SHORT if score < 0 else Direction.FLAT
        return self._opinion(direction, _clip01(abs(score)), evidence)


class SentimentAnalyst(Analyst):
    """Reads the ``sentiment`` side-channel (social score in [-1, 1])."""

    name = "Sentiment Analyst"
    category = "sentiment"

    def analyze(self, snapshot: MarketSnapshot, context=None) -> AnalystOpinion:
        sent = snapshot.sentiment or {}
        if "score" not in sent:
            return self._abstain("no sentiment score supplied")
        raw = float(sent["score"])
        impact = float(np.tanh(raw * 2))
        direction = Direction.LONG if impact > 0 else Direction.SHORT if impact < 0 else Direction.FLAT
        ev = [Evidence("social", f"Aggregated social sentiment {raw:+.2f}", impact, raw)]
        # A contrarian flag flips extreme crowd positioning.
        if sent.get("contrarian") and abs(raw) > 0.8:
            direction = Direction.SHORT if direction is Direction.LONG else Direction.LONG
            ev.append(Evidence("contrarian", "Crowd extreme — faded", -impact))
        return self._opinion(direction, _clip01(abs(impact)), ev)


class OnchainAnalyst(Analyst):
    """Reads the ``onchain`` side-channel (exchange flows, whale accumulation)."""

    name = "On-chain Analyst"
    category = "onchain"

    def analyze(self, snapshot: MarketSnapshot, context=None) -> AnalystOpinion:
        oc = snapshot.onchain or {}
        if not oc:
            return self._abstain("no on-chain data supplied")
        evidence: list[Evidence] = []
        score = 0.0
        # net_exchange_flow: negative (outflow) is bullish (coins leaving to cold storage).
        if "net_exchange_flow" in oc:
            impact = -float(np.tanh(oc["net_exchange_flow"]))
            score += 0.6 * impact
            evidence.append(Evidence("exchange_flow", f"Net exchange flow {oc['net_exchange_flow']:+.2f}", 0.6 * impact))
        # whale_accumulation: +1 accumulating.
        if "whale_accumulation" in oc:
            impact = float(np.tanh(oc["whale_accumulation"]))
            score += 0.4 * impact
            evidence.append(Evidence("whales", f"Whale accumulation {oc['whale_accumulation']:+.2f}", 0.4 * impact))
        if not evidence:
            return self._abstain("on-chain channel present but empty")
        direction = Direction.LONG if score > 0 else Direction.SHORT if score < 0 else Direction.FLAT
        return self._opinion(direction, _clip01(abs(score)), evidence)


class StatisticalAnalyst(Analyst):
    """Mean-reversion / momentum blend from price statistics (always available)."""

    name = "Statistical Analyst"
    category = "statistical"

    def __init__(self, window: int = 50) -> None:
        self.window = window

    def analyze(self, snapshot: MarketSnapshot, context=None) -> AnalystOpinion:
        close = snapshot.close
        if len(close) < self.window + 2:
            return self._abstain("insufficient history for statistics")
        z = ind.zscore(close, self.window).iloc[-1]
        mom = close.pct_change(self.window).iloc[-1]
        if np.isnan(z):
            return self._abstain("z-score undefined (zero variance)")

        # Momentum favours the trend; z-score adds mild mean-reversion pull.
        mom_impact = float(np.tanh(mom * 5))
        rev_impact = -float(np.tanh(z / 3)) * 0.4
        score = 0.7 * mom_impact + rev_impact
        evidence = [
            Evidence("momentum", f"{self.window}-bar momentum {mom:+.2%}", 0.7 * mom_impact, round(float(mom), 5)),
            Evidence("zscore", f"Price z-score {z:+.2f}", rev_impact, round(float(z), 3)),
        ]
        direction = Direction.LONG if score > 0 else Direction.SHORT if score < 0 else Direction.FLAT
        return self._opinion(direction, _clip01(abs(score)), evidence)


def default_analysts() -> list[Analyst]:
    """The standard panel. Data-hungry analysts abstain when their channel is
    missing, so this panel is safe to run on OHLCV-only snapshots."""
    return [
        TechnicalAnalyst(),
        StatisticalAnalyst(),
        MacroAnalyst(),
        OnchainAnalyst(),
        SentimentAnalyst(),
    ]
