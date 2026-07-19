"""LLM-backed committee analyst (module 2, M6 WP-6.2).

:class:`LLMAnalyst` plugs a language model into the existing ``Analyst`` ABC
— the committee needs **zero changes** to host it (I7). The model is asked
for a structured JSON opinion over the facts already inside the snapshot;
the response is validated strictly and turned into a normal
:class:`~quantos.committee.base.AnalystOpinion` **with evidence** (I4).

Honesty is non-negotiable (I3): on *any* failure — client error, timeout,
malformed JSON, out-of-range fields, empty evidence, a sub-floor confidence,
or the model abstaining itself — the analyst **abstains** with the reason
recorded. An LLM can add insight; it can never fabricate conviction.
"""

from __future__ import annotations

import json
from typing import Any

from quantos.committee.base import Analyst, AnalystOpinion, Direction, Evidence
from quantos.data.models import MarketSnapshot
from quantos.llm.client import LLMClient

__all__ = ["LLM_CATEGORIES", "LLMAnalyst", "OPINION_SCHEMA", "llm_bench"]

#: Categories the default LLM bench covers (mirrors the rule-based bench).
LLM_CATEGORIES: tuple[str, ...] = ("technical", "statistical", "macro", "sentiment", "onchain")

#: The structured response contract sent to the model with every request.
OPINION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["direction", "confidence", "evidence"],
    "properties": {
        "direction": {"enum": ["LONG", "FLAT", "SHORT"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "abstain": {"type": "boolean"},
        "evidence": {
            "type": "array",
            "minItems": 1,
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
        "rationale": {"type": "string"},
    },
}

#: Snapshot channels each category is fed (OHLCV-driven ones get none).
_CATEGORY_CHANNELS: dict[str, tuple[str, ...]] = {
    "technical": (),
    "statistical": (),
    "macro": ("macro", "events"),
    "sentiment": ("sentiment", "news"),
    "onchain": ("onchain",),
    "derivatives": ("derivatives",),
}


class _MalformedOpinion(ValueError):
    """Internal: the model's response failed strict validation."""


def _strip_fences(raw: str) -> str:
    """Remove a Markdown code fence if the model wrapped its JSON in one."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


class LLMAnalyst(Analyst):
    """A committee specialist whose analysis is produced by an LLM.

    Reads only what is already inside the snapshot/context (I2), asks the
    client for a structured opinion, validates it strictly and abstains on
    any deviation (I3). With the deterministic
    :class:`~quantos.llm.client.MockLLMClient` the whole deliberation
    replays bit-for-bit (I8).
    """

    def __init__(
        self,
        category: str,
        client: LLMClient,
        name: str | None = None,
        min_confidence: float = 0.05,
    ) -> None:
        """
        Args:
            category: the specialist category (weighs into aggregation).
            client: any :class:`~quantos.llm.client.LLMClient` backend.
            name: display name; a category-derived default when omitted.
            min_confidence: floor under which a parsed opinion is treated as
                a low-confidence parse and abstained (I3).
        """
        super().__init__(name=name or f"LLM {category.title()} Analyst", category=category)
        self.client = client
        self.min_confidence = min_confidence

    # -- prompt ------------------------------------------------------------

    def _facts(self, snapshot: MarketSnapshot, context: dict[str, Any] | None) -> dict[str, Any]:
        """The deterministic fact sheet the model reasons over (I2/I8)."""
        close = snapshot.ohlcv["close"]
        facts: dict[str, Any] = {
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "as_of": snapshot.as_of,
            "bars": snapshot.bars,
            "last_price": snapshot.last_price,
        }
        if snapshot.bars >= 21:
            facts["return_1"] = round(float(close.pct_change(1).iloc[-1]), 6)
            facts["return_5"] = round(float(close.pct_change(5).iloc[-1]), 6)
            facts["return_20"] = round(float(close.pct_change(20).iloc[-1]), 6)
            facts["volatility_20"] = round(float(close.pct_change().tail(20).std()), 6)
        for channel in _CATEGORY_CHANNELS.get(self.category, ()):
            value = getattr(snapshot, channel, None)
            if value:
                facts[channel] = value
        regime = (context or {}).get("regime")
        if isinstance(regime, dict) and regime.get("label"):
            facts["regime"] = regime["label"]
        return facts

    def _prompt(self, snapshot: MarketSnapshot, context: dict[str, Any] | None) -> str:
        """Build the structured request (the word "analyst" keys the mock)."""
        facts = json.dumps(self._facts(snapshot, context), sort_keys=True, default=str)
        lines = [
            f"You are the {self.category} analyst on an investment committee "
            "for a research-only platform (no live trading, I1).",
            f"Market facts (JSON): {facts}",
        ]
        debate = (context or {}).get("debate")
        if isinstance(debate, dict) and debate.get("peer_summary"):
            lines.append(
                "Debate round — your peers' first-round stances: "
                f"{json.dumps(debate['peer_summary'], sort_keys=True)}. "
                "You may revise your opinion once in light of them."
            )
        challenge = (context or {}).get("challenge")
        if isinstance(challenge, dict) and challenge.get("argument"):
            lines.append(
                "A devil's-advocate challenger contested the provisional decision: "
                f"{json.dumps(challenge, sort_keys=True, default=str)}. "
                "Weigh the objection explicitly."
            )
        lines.append(
            "Return your opinion as strict JSON with keys: direction "
            '("LONG"|"FLAT"|"SHORT"), confidence (0..1), abstain (bool), '
            "evidence (non-empty array of {name, detail, impact in [-1,1], value}), "
            "rationale. If you lack usable data, set abstain=true — never "
            "fabricate conviction."
        )
        return "\n".join(lines)

    # -- response validation ----------------------------------------------

    def _parse(self, raw: str) -> AnalystOpinion:
        """Strictly validate the model's JSON into an opinion.

        Raises:
            _MalformedOpinion: on any structural or range violation — the
                caller abstains (I3); nothing is silently repaired.
        """
        try:
            payload = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise _MalformedOpinion(f"malformed JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise _MalformedOpinion("response must be a JSON object")

        if payload.get("abstain") is True:
            reason = str(payload.get("rationale") or "model chose to abstain")
            return self._abstain(f"model abstained: {reason}")

        direction_raw = payload.get("direction")
        if direction_raw not in {d.value for d in Direction}:
            raise _MalformedOpinion(f"invalid direction {direction_raw!r}")
        direction = Direction(direction_raw)

        raw_confidence = payload.get("confidence")
        if not isinstance(raw_confidence, (int, float)) or isinstance(raw_confidence, bool):
            raise _MalformedOpinion("confidence is not a number")
        confidence = float(raw_confidence)
        if not 0.0 <= confidence <= 1.0:
            raise _MalformedOpinion(f"confidence {confidence} outside [0, 1]")
        if confidence < self.min_confidence:
            return self._abstain(
                f"low-confidence parse: model confidence {confidence:.3f} "
                f"below the {self.min_confidence:.3f} floor"
            )

        items = payload.get("evidence")
        if not isinstance(items, list) or not items:
            raise _MalformedOpinion("evidence must be a non-empty array")
        evidence: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                raise _MalformedOpinion("each evidence entry must be an object")
            try:
                impact = float(item["impact"])
                name = str(item["name"])
                detail = str(item["detail"])
            except (KeyError, TypeError, ValueError) as exc:
                raise _MalformedOpinion(f"bad evidence entry: {exc}") from exc
            if not -1.0 <= impact <= 1.0:
                raise _MalformedOpinion(f"evidence impact {impact} outside [-1, 1]")
            value = item.get("value")
            evidence.append(
                Evidence(
                    name=name,
                    detail=detail,
                    impact=impact,
                    value=float(value) if isinstance(value, (int, float)) else None,
                )
            )
        rationale = payload.get("rationale")
        if isinstance(rationale, str) and rationale:
            evidence.append(Evidence(name="llm_rationale", detail=rationale, impact=0.0))

        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=direction,
            confidence=confidence,
            evidence=evidence,
        )

    # -- the Analyst contract ----------------------------------------------

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        """Ask the model for an opinion; abstain honestly on any failure (I3)."""
        try:
            raw = self.client.complete(self._prompt(snapshot, context), schema=OPINION_SCHEMA)
        except Exception as exc:  # noqa: BLE001 - any client failure abstains (I3)
            return self._abstain(f"LLM call failed: {exc}")
        try:
            return self._parse(raw)
        except _MalformedOpinion as exc:
            return self._abstain(f"malformed LLM response: {exc}")


def llm_bench(client: LLMClient, categories: tuple[str, ...] = LLM_CATEGORIES) -> list[Analyst]:
    """A full LLM analyst bench sharing one client (one per category)."""
    return [LLMAnalyst(category, client) for category in categories]
