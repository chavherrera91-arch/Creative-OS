"""WP-6.2 — LLM-backed analyst.

Acceptance: with the deterministic ``MockLLMClient`` the analyst yields a
valid ``AnalystOpinion`` **with evidence** and plugs into the
``InvestmentCommittee`` with zero committee changes (I7), keeping the
decision fully auditable (I4) and reproducible (I8); on *any* failure —
client error, malformed JSON, out-of-range fields, empty evidence,
low-confidence parse, model self-abstention — it **abstains** honestly (I3).
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.committee.llm import LLM_CATEGORIES, LLMAnalyst, llm_bench
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import explain_decision
from quantos.llm.client import MockLLMClient


def snapshot(ohlcv: pd.DataFrame | None = None, **channels: Any) -> MarketSnapshot:
    frame = ohlcv if ohlcv is not None else make_ohlcv()
    return MarketSnapshot("BTC/USDT", "1h", frame, **channels)


class ScriptedClient:
    """Returns a fixed payload (or raises) — for exercising failure paths."""

    def __init__(self, payload: str | Exception) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        self.prompts.append(prompt)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def valid_payload(**overrides: Any) -> str:
    base: dict[str, Any] = {
        "direction": "LONG",
        "confidence": 0.6,
        "abstain": False,
        "evidence": [
            {"name": "funding", "detail": "funding is deeply negative", "impact": 0.5, "value": -3}
        ],
        "rationale": "shorts pay longs; squeeze risk",
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Happy path — valid opinion with evidence, deterministic
# ---------------------------------------------------------------------------


class TestValidOpinion:
    def test_mock_client_yields_a_valid_opinion(self) -> None:
        analyst = LLMAnalyst("technical", MockLLMClient(seed=1))
        opinion = analyst.analyze(snapshot())
        assert isinstance(opinion, AnalystOpinion)
        assert not opinion.abstained
        assert opinion.category == "technical"
        assert opinion.direction in Direction
        assert 0.0 <= opinion.confidence <= 1.0
        assert opinion.evidence  # never an opinion without evidence (I4)

    def test_deterministic_replay(self) -> None:
        """Same snapshot + same seeded client -> identical opinion (I8)."""
        snap = snapshot()
        a = LLMAnalyst("technical", MockLLMClient(seed=3)).analyze(snap)
        b = LLMAnalyst("technical", MockLLMClient(seed=3)).analyze(snap)
        assert a.as_dict() == b.as_dict()

    def test_scripted_response_is_parsed_faithfully(self) -> None:
        analyst = LLMAnalyst("derivatives", ScriptedClient(valid_payload()))
        opinion = analyst.analyze(snapshot(derivatives={"funding_rate": -0.03}))
        assert opinion.direction is Direction.LONG
        assert opinion.confidence == 0.6
        assert opinion.evidence[0].name == "funding"
        assert opinion.evidence[0].value == -3.0
        # the rationale is preserved as neutral evidence (auditable, I4)
        assert any(e.name == "llm_rationale" for e in opinion.evidence)

    def test_code_fenced_json_is_accepted(self) -> None:
        fenced = f"```json\n{valid_payload()}\n```"
        opinion = LLMAnalyst("technical", ScriptedClient(fenced)).analyze(snapshot())
        assert not opinion.abstained and opinion.direction is Direction.LONG

    def test_prompt_carries_facts_channel_and_regime(self) -> None:
        client = ScriptedClient(valid_payload())
        LLMAnalyst("sentiment", client).analyze(
            snapshot(sentiment={"score": 0.7}),
            context={"regime": {"label": "TREND_UP", "tradeable": True}},
        )
        prompt = client.prompts[0]
        assert "sentiment analyst" in prompt
        assert "BTC/USDT" in prompt and '"score": 0.7' in prompt
        assert "TREND_UP" in prompt
        assert "no live trading" in prompt  # the research-only stance (I1)


# ---------------------------------------------------------------------------
# Honest abstention on every failure mode (I3)
# ---------------------------------------------------------------------------


class TestAbstention:
    @pytest.mark.parametrize(
        ("payload", "match"),
        [
            (RuntimeError("timeout after 30s"), "LLM call failed"),
            ("this is not json at all", "malformed JSON"),
            (json.dumps(["not", "an", "object"]), "JSON object"),
            (valid_payload(direction="SIDEWAYS"), "invalid direction"),
            (valid_payload(confidence="very high"), "not a number"),
            (valid_payload(confidence=1.7), "outside"),
            (valid_payload(evidence=[]), "non-empty"),
            (
                valid_payload(evidence=[{"name": "x", "detail": "y", "impact": 2.0}]),
                "outside",
            ),
            (valid_payload(evidence=[{"detail": "impact missing"}]), "bad evidence"),
        ],
    )
    def test_any_failure_abstains(self, payload: str | Exception, match: str) -> None:
        opinion = LLMAnalyst("technical", ScriptedClient(payload)).analyze(snapshot())
        assert opinion.abstained
        assert opinion.confidence == 0.0
        assert match in opinion.evidence[0].detail  # the reason is recorded (I4)

    def test_model_self_abstention_is_honoured(self) -> None:
        payload = json.dumps({"abstain": True, "rationale": "no on-chain data provided"})
        opinion = LLMAnalyst("onchain", ScriptedClient(payload)).analyze(snapshot())
        assert opinion.abstained
        assert "no on-chain data" in opinion.evidence[0].detail

    def test_low_confidence_parse_abstains(self) -> None:
        opinion = LLMAnalyst(
            "technical", ScriptedClient(valid_payload(confidence=0.01))
        ).analyze(snapshot())
        assert opinion.abstained
        assert "low-confidence" in opinion.evidence[0].detail


# ---------------------------------------------------------------------------
# Plugs into the committee unchanged (I7); decision stays auditable (I4)
# ---------------------------------------------------------------------------


class TestCommitteeIntegration:
    def test_llm_analyst_joins_the_default_bench(self) -> None:
        committee = default_committee()
        committee.analysts.append(LLMAnalyst("technical", MockLLMClient(seed=2)))
        decision = committee.deliberate(snapshot())
        record = decision.as_dict()
        json.dumps(record)  # complete and serialisable (I4)
        names = [o["analyst"] for o in record["opinions"]]
        assert "LLM Technical Analyst" in names
        assert "LLM Technical Analyst" in record["run_manifest"]["analysts"]

    def test_all_llm_committee_runs_offline(self) -> None:
        """A full LLM bench deliberates with the mock — no keys, no net (I6)."""
        committee = InvestmentCommittee(analysts=llm_bench(MockLLMClient(seed=4)))
        decision = committee.deliberate(snapshot())
        assert len(decision.opinions) == len(LLM_CATEGORIES)
        json.dumps(decision.as_dict())
        replay = committee.deliberate(snapshot())
        assert replay.as_dict() == decision.as_dict()  # reproducible (I8)

    def test_abstaining_llm_analyst_is_excluded_from_aggregation(self) -> None:
        """A broken LLM never moves the needle (I3)."""
        committee = default_committee()
        baseline = committee.deliberate(snapshot())
        committee.analysts.append(
            LLMAnalyst("llm-broken", ScriptedClient(RuntimeError("provider down")))
        )
        decision = committee.deliberate(snapshot())
        assert decision.confidence == baseline.confidence
        assert decision.direction == baseline.direction
        assert decision.confidence_report is not None
        assert "LLM Llm-Broken Analyst" in decision.confidence_report.abstentions
        # ... and the abstention is visible in the human report (I4)
        assert "ABSTAINED" in explain_decision(decision)
