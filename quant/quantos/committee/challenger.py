"""AI Challenger — the committee's official devil's advocate (module 17, WP-6.4).

Before a provisional decision is finalised, the Challenger tries to break
it: it argues the **opposite** side with counter-evidence drawn from the
same snapshot, the same opinions and the same regime — never from new data
(I2). A *material* objection makes the orchestrator run **one** more
deliberation round with the objection in context; the decision then records
whether the objection was decisive (I4).

The Challenger has **no veto** — that power is the Risk Manager's alone
(I5). It can only force reconsideration; and a challenger that fails
(malformed LLM output, error, timeout) fails **safe**: it agrees, forcing
nothing (the mirror of analyst abstention, I3).

Two implementations behind one Protocol (I7): the deterministic
:class:`RuleChallenger` (offline default) and the optional
:class:`LLMChallenger` behind the M6 :class:`~quantos.llm.client.LLMClient`
port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quantos.committee.base import Direction, Evidence
from quantos.committee.decision import CommitteeDecision
from quantos.data.models import MarketSnapshot
from quantos.features import indicators as ind
from quantos.llm.client import LLMClient

__all__ = ["CHALLENGE_SCHEMA", "ChallengeResult", "Challenger", "LLMChallenger", "RuleChallenger"]

#: The structured response contract sent to an LLM challenger.
CHALLENGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["agrees", "material", "argument", "counter_evidence"],
    "properties": {
        "agrees": {"type": "boolean"},
        "material": {"type": "boolean"},
        "argument": {"type": "string"},
        "counter_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "detail", "impact"],
                "properties": {
                    "name": {"type": "string"},
                    "detail": {"type": "string"},
                    "impact": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                    "value": {"type": ["number", "null"]},
                },
            },
        },
    },
}


@dataclass
class ChallengeResult:
    """The Challenger's verdict on a provisional decision.

    Attributes:
        agrees: True when the Challenger found nothing worth contesting.
        material: True when the objection is strong enough to force one
            extra deliberation round (never a veto, I5).
        argument: the Challenger's stated case (auditable, I4).
        counter_evidence: signed evidence *against* the provisional
            direction (impacts oppose the decision's sign).
        challenger: name of the emitting challenger.
    """

    agrees: bool
    material: bool
    argument: str
    counter_evidence: list[Evidence] = field(default_factory=list)
    challenger: str = "Challenger"

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "challenger": self.challenger,
            "agrees": self.agrees,
            "material": self.material,
            "argument": self.argument,
            "counter_evidence": [e.as_dict() for e in self.counter_evidence],
        }


@runtime_checkable
class Challenger(Protocol):
    """The devil's-advocate port (ARCHITECTURE §2.4, I7)."""

    name: str

    def contest(self, decision: CommitteeDecision, snapshot: MarketSnapshot) -> ChallengeResult:
        """Argue the opposite side of a provisional decision."""
        ...


def _nothing_to_contest(name: str, decision: CommitteeDecision) -> ChallengeResult:
    """The agreement result for decisions that already stand down."""
    outcome = "vetoed" if decision.blocked_by_risk else "standing down"
    return ChallengeResult(
        agrees=True,
        material=False,
        argument=f"nothing to contest: the committee is already {outcome} "
        f"({decision.direction.value})",
        challenger=name,
    )


class RuleChallenger:
    """Deterministic devil's advocate (offline default, I6/I8).

    Builds the case against an approved directional call from three sources,
    all already on the table: (1) the strongest opposing evidence inside the
    committee's own opinions, (2) fresh stretch statistics from the same
    OHLCV (z-score over-extension, RSI extreme, elevated volatility), and
    (3) a regime that contradicts the direction. The objection is *material*
    when the counters' mean absolute impact clears ``material_threshold``.
    """

    #: Bars needed before the stretch statistics are computed.
    MIN_BARS = 30

    def __init__(self, name: str = "Rule Challenger", material_threshold: float = 0.3) -> None:
        """
        Args:
            name: display name recorded on every result.
            material_threshold: minimum mean |impact| of the counter-evidence
                for the objection to force an extra round.
        """
        self.name = name
        self.material_threshold = material_threshold

    def _peer_counters(self, decision: CommitteeDecision, sign: int) -> list[Evidence]:
        """The strongest opposing evidence the committee itself produced."""
        opposing = sorted(
            (
                e
                for opinion in decision.opinions
                if not opinion.abstained
                for e in opinion.evidence
                if e.impact * sign < 0
            ),
            key=lambda e: abs(e.impact),
            reverse=True,
        )
        return [
            Evidence(
                name=f"peer_{e.name}",
                detail=f"the committee's own record argues against "
                f"{decision.direction.value}: {e.detail}",
                impact=e.impact,
                value=e.value,
            )
            for e in opposing[:3]
        ]

    def _stretch_counters(self, snapshot: MarketSnapshot, sign: int) -> list[Evidence]:
        """Fresh over-extension statistics from the same OHLCV (I2)."""
        if snapshot.bars < self.MIN_BARS:
            return []
        close = snapshot.ohlcv["close"]
        counters: list[Evidence] = []

        z = float(ind.zscore(close, 20).iloc[-1])
        if z * sign > 1.5:
            counters.append(
                Evidence(
                    name="overextension",
                    detail=f"price is {z:+.2f}σ from its 20-bar mean — this entry chases "
                    "a stretched move",
                    impact=-sign * min(1.0, abs(z) / 2.5),
                    value=z,
                )
            )

        rsi = float(ind.rsi(close, 14).iloc[-1])
        if (sign > 0 and rsi > 70.0) or (sign < 0 and rsi < 30.0):
            counters.append(
                Evidence(
                    name="rsi_extreme",
                    detail=f"RSI(14) at {rsi:.1f} is an "
                    f"{'overbought' if sign > 0 else 'oversold'} extreme — reversal risk",
                    impact=-sign * min(1.0, abs(rsi - 50.0) / 50.0),
                    value=rsi,
                )
            )

        vol = ind.rolling_volatility(close, 20)
        vol_med = float(vol.median())
        ratio = float(vol.iloc[-1]) / vol_med if vol_med > 0 else 1.0
        if ratio > 1.5:
            counters.append(
                Evidence(
                    name="volatility_elevated",
                    detail=f"realised volatility runs {ratio:.2f}x its median — adverse "
                    "moves are amplified",
                    impact=-sign * min(1.0, (ratio - 1.0) / 2.0),
                    value=ratio,
                )
            )
        return counters

    def _regime_counter(self, decision: CommitteeDecision, sign: int) -> list[Evidence]:
        """A classified regime that contradicts the direction."""
        label = str(decision.regime.get("label", "")) if decision.regime else ""
        against_long = {"TREND_DOWN", "CRISIS", "HIGH_VOL"}
        against_short = {"TREND_UP", "CRISIS", "HIGH_VOL"}
        opposed = (sign > 0 and label in against_long) or (sign < 0 and label in against_short)
        if not opposed:
            return []
        return [
            Evidence(
                name="regime_mismatch",
                detail=f"the classified regime is {label} — it does not favour "
                f"a {decision.direction.value} entry",
                impact=-sign * 0.5,
                value=None,
            )
        ]

    def contest(self, decision: CommitteeDecision, snapshot: MarketSnapshot) -> ChallengeResult:
        """Argue the opposite side; material only when the case is strong.

        Deterministic: the same decision + snapshot always produce the same
        challenge (I8).
        """
        if not decision.approved or decision.direction is Direction.FLAT:
            return _nothing_to_contest(self.name, decision)
        sign = decision.direction.sign
        counters = (
            self._peer_counters(decision, sign)
            + self._stretch_counters(snapshot, sign)
            + self._regime_counter(decision, sign)
        )
        if not counters:
            return ChallengeResult(
                agrees=True,
                material=False,
                argument=f"no credible case against {decision.direction.value} was found "
                "in the record or the tape",
                challenger=self.name,
            )
        strength = sum(abs(e.impact) for e in counters) / len(counters)
        material = strength >= self.material_threshold
        argument = (
            f"the case against {decision.direction.value}: "
            + "; ".join(e.name for e in counters)
            + f" (strength {strength:.2f}, material threshold {self.material_threshold:.2f})"
        )
        return ChallengeResult(
            agrees=False,
            material=material,
            argument=argument,
            counter_evidence=counters,
            challenger=self.name,
        )


class LLMChallenger:
    """LLM-backed devil's advocate behind the :class:`LLMClient` port.

    The model is shown the provisional decision's own record (direction,
    confidence, top evidence, regime) and asked to contest it as strict
    JSON. Validation is unforgiving, and failure is **fail-safe**: any
    error or malformed response yields agreement — an erroring challenger
    can never force a re-debate, let alone a veto (I3/I5). Counter-evidence
    that *supports* the decision is dropped; a "material" objection without
    surviving counter-evidence is downgraded — objections need evidence.
    """

    def __init__(self, client: LLMClient, name: str = "LLM Challenger") -> None:
        self.client = client
        self.name = name

    def _prompt(self, decision: CommitteeDecision, snapshot: MarketSnapshot) -> str:
        """Build the contest request (keys the mock's challenge branch)."""
        sign = decision.direction.sign
        supporting = [
            e.as_dict()
            for opinion in decision.opinions
            if not opinion.abstained
            for e in opinion.evidence
            if e.impact * sign > 0
        ][:6]
        summary = {
            "symbol": decision.symbol,
            "as_of": decision.as_of,
            "confidence": decision.confidence,
            "regime": decision.regime.get("label") if decision.regime else None,
            "supporting_evidence": supporting,
        }
        return (
            "You are the committee's devil's advocate on a research-only investment "
            "committee (no live trading, I1). Argue the OPPOSITE side of this call "
            "using only the record below.\n"
            f"provisional decision: {decision.direction.value} "
            f"(approved={decision.approved})\n"
            f"Decision record (JSON): {json.dumps(summary, sort_keys=True, default=str)}\n"
            "Respond with strict JSON: {agrees (bool), material (bool), argument "
            "(string), counter_evidence (array of {name, detail, impact in [-1,1], "
            "value})}. Impacts must oppose the decision's direction. Set "
            "material=true only for an objection strong enough to force one more "
            "deliberation round — you have no veto."
        )

    def _parse(self, raw: str, sign: int) -> ChallengeResult:
        """Strictly validate the model's JSON into a :class:`ChallengeResult`.

        Raises:
            ValueError: on any structural violation (the caller fails safe).
        """
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("challenge response must be a JSON object")
        agrees = payload.get("agrees")
        material = payload.get("material")
        if not isinstance(agrees, bool) or not isinstance(material, bool):
            raise ValueError("agrees/material must be booleans")
        argument = str(payload.get("argument") or "")
        items = payload.get("counter_evidence")
        if not isinstance(items, list):
            raise ValueError("counter_evidence must be an array")
        counters: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("each counter-evidence entry must be an object")
            impact = float(item["impact"])
            if not -1.0 <= impact <= 1.0:
                raise ValueError(f"counter-evidence impact {impact} outside [-1, 1]")
            if impact * sign > 0:
                continue  # supporting "counter"-evidence is nonsense: dropped
            value = item.get("value")
            counters.append(
                Evidence(
                    name=str(item["name"]),
                    detail=str(item["detail"]),
                    impact=impact,
                    value=float(value) if isinstance(value, (int, float)) else None,
                )
            )
        if agrees:
            material = False
        if material and not counters:
            material = False
            argument = f"{argument} [downgraded: a material objection needs counter-evidence]"
        return ChallengeResult(
            agrees=agrees,
            material=material,
            argument=argument,
            counter_evidence=counters,
            challenger=self.name,
        )

    def contest(self, decision: CommitteeDecision, snapshot: MarketSnapshot) -> ChallengeResult:
        """Contest via the LLM; agree (fail-safe) on any failure."""
        if not decision.approved or decision.direction is Direction.FLAT:
            return _nothing_to_contest(self.name, decision)
        sign = decision.direction.sign
        try:
            raw = self.client.complete(self._prompt(decision, snapshot), schema=CHALLENGE_SCHEMA)
            return self._parse(raw, sign)
        except Exception as exc:  # noqa: BLE001 - a failing challenger forces nothing
            return ChallengeResult(
                agrees=True,
                material=False,
                argument=f"challenger failed safe (forcing nothing): {exc}",
                challenger=self.name,
            )
