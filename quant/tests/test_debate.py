"""WP-6.3 — Debate orchestrator.

Acceptance: the debate produces a valid, auditable ``CommitteeDecision``
offline — the same type as the default orchestrator, with the debate round
recorded in the run manifest and surfaced in the report (I4); analysts see a
peer summary and may revise exactly once; the decision hierarchy is
unchanged (regime gate ▶ risk veto ▶ threshold) and the risk veto stays
absolute (I5); LangGraph is optional and lazily imported (I6); the whole
debate replays bit-for-bit (I8).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.committee.analysts import default_analysts
from quantos.committee.base import Analyst, AnalystOpinion, Direction, Evidence
from quantos.committee.committee import InvestmentCommittee
from quantos.committee.debate import DebateCommittee, peer_summary
from quantos.committee.decision import CommitteeDecision
from quantos.committee.llm import LLMAnalyst
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import explain_decision
from quantos.llm.client import MockLLMClient


def snapshot(ohlcv: pd.DataFrame | None = None) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", ohlcv if ohlcv is not None else make_ohlcv())


class Stub(Analyst):
    """A fixed-opinion analyst (never revises)."""

    def __init__(self, name: str, category: str, direction: Direction, conf: float = 0.9) -> None:
        super().__init__(name=name, category=category)
        self._direction = direction
        self._conf = conf

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        sign = float(self._direction.sign) * self._conf
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=self._direction,
            confidence=self._conf,
            evidence=[Evidence(name="stub", detail=f"fixed {self._direction.value}", impact=sign)],
        )


class Flipper(Analyst):
    """LONG in round 1; flips SHORT once it sees the debate context."""

    def __init__(self) -> None:
        super().__init__(name="Flipper", category="technical")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        if context and "debate" in context:
            return AnalystOpinion(
                analyst=self.name,
                category=self.category,
                direction=Direction.SHORT,
                confidence=0.9,
                evidence=[Evidence(name="flip", detail="revised after peer debate", impact=-0.9)],
            )
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.LONG,
            confidence=0.9,
            evidence=[Evidence(name="orig", detail="initial view", impact=0.9)],
        )


class RecordingLLMClient:
    """A valid-opinion client that records every prompt it is asked."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "direction": "LONG",
                "confidence": 0.5,
                "abstain": False,
                "evidence": [{"name": "sig", "detail": "steady bid", "impact": 0.5, "value": 1}],
                "rationale": "same view either round",
            }
        )


# ---------------------------------------------------------------------------
# The debate produces the same auditable decision type (I4)
# ---------------------------------------------------------------------------


class TestDebateDecision:
    def test_valid_auditable_decision_offline(self) -> None:
        committee = DebateCommittee(analysts=default_analysts())
        decision = committee.deliberate(snapshot())
        assert isinstance(decision, CommitteeDecision)
        record = decision.as_dict()
        json.dumps(record)  # complete and serialisable (I4)
        debate = record["run_manifest"]["debate"]
        assert debate["protocol"] == "peer-summary-revise-once"
        assert debate["rounds"] == 2
        assert len(debate["first_round"]) == len(committee.analysts)
        assert debate["revised"] == []  # deterministic rule analysts reaffirm
        # ... and the debate is visible in the human report (I4)
        assert "debate protocol" in explain_decision(decision)

    def test_rule_bench_debate_matches_the_plain_committee(self) -> None:
        """Deterministic analysts don't revise -> same outcome as M1 flow."""
        snap = snapshot()
        plain = InvestmentCommittee(analysts=default_analysts()).deliberate(snap)
        debated = DebateCommittee(analysts=default_analysts()).deliberate(snap)
        assert debated.direction == plain.direction
        assert debated.approved == plain.approved
        assert debated.confidence == plain.confidence

    def test_reproducible(self) -> None:
        """Same snapshot + same seeded mock bench -> identical decision (I8)."""
        committee = DebateCommittee(
            analysts=[LLMAnalyst("technical", MockLLMClient(seed=5)), Flipper()]
        )
        snap = snapshot()
        assert committee.deliberate(snap).as_dict() == committee.deliberate(snap).as_dict()


# ---------------------------------------------------------------------------
# Analysts see peers and may revise exactly once
# ---------------------------------------------------------------------------


class TestRevision:
    def test_a_revising_analyst_changes_the_outcome(self) -> None:
        snap = snapshot()
        plain = InvestmentCommittee(analysts=[Flipper()]).deliberate(snap)
        assert plain.direction is Direction.LONG  # no debate, no flip
        debated = DebateCommittee(analysts=[Flipper()]).deliberate(snap)
        assert debated.direction is Direction.SHORT  # the revision decided
        assert debated.run_manifest["debate"]["revised"] == ["Flipper"]
        # the recorded opinions are the final (revised) round
        assert debated.opinions[0].direction is Direction.SHORT
        # ... while round 1 stays auditable in the manifest (I4)
        assert debated.run_manifest["debate"]["first_round"][0]["direction"] == "LONG"

    def test_llm_analyst_receives_the_peer_summary(self) -> None:
        client = RecordingLLMClient()
        bench: list[Analyst] = [
            Stub("Perma-Bull", "statistical", Direction.LONG),
            LLMAnalyst("technical", client),
        ]
        DebateCommittee(analysts=bench).deliberate(snapshot())
        assert len(client.prompts) == 2  # one opinion + exactly one revision
        assert "Debate round" not in client.prompts[0]
        assert "Debate round" in client.prompts[1]
        assert "Perma-Bull" in client.prompts[1]  # peers are named
        assert "revise your opinion once" in client.prompts[1]

    def test_peer_summary_shape(self) -> None:
        opinions = [Stub("A", "technical", Direction.LONG).analyze(snapshot())]
        summary = peer_summary(opinions)
        assert summary == [
            {
                "analyst": "A",
                "category": "technical",
                "direction": "LONG",
                "confidence": 0.9,
                "abstained": False,
                "headline": "fixed LONG",
            }
        ]


# ---------------------------------------------------------------------------
# The hierarchy is unchanged: regime gate ▶ risk veto (I5) ▶ threshold
# ---------------------------------------------------------------------------


class TestHierarchy:
    def bull_bench(self) -> list[Analyst]:
        return [
            Stub("Bull-1", "technical", Direction.LONG),
            Stub("Bull-2", "statistical", Direction.LONG),
        ]

    def test_risk_veto_is_still_absolute(self) -> None:
        """A unanimous 90% LONG debate is blocked by one veto (I5)."""
        decision = DebateCommittee(analysts=self.bull_bench()).deliberate(
            snapshot(), context={"daily_pnl_pct": -0.10}
        )
        assert decision.blocked_by_risk
        assert decision.direction is Direction.FLAT
        assert not decision.approved
        assert any("risk veto" in reason for reason in decision.reasons)

    def test_regime_gate_precedes_everything(self) -> None:
        decision = DebateCommittee(analysts=self.bull_bench()).deliberate(
            snapshot(), context={"regime": {"label": "CRISIS", "tradeable": False}}
        )
        assert not decision.approved
        assert decision.direction is Direction.FLAT
        assert not decision.blocked_by_risk
        assert "regime gate" in decision.reasons[0]

    def test_threshold_still_applies(self) -> None:
        weak = [Stub("Meek", "technical", Direction.LONG, conf=0.1)]
        decision = DebateCommittee(analysts=weak).deliberate(snapshot())
        assert not decision.approved
        assert any("standing down" in reason for reason in decision.reasons)


# ---------------------------------------------------------------------------
# LangGraph is optional and lazy (I6)
# ---------------------------------------------------------------------------


class TestLangGraph:
    def test_lazy_and_never_required(self) -> None:
        committee = DebateCommittee(analysts=default_analysts(), use_langgraph=True)
        assert "langgraph" not in sys.modules  # constructing imports nothing
        with pytest.raises(ImportError, match="langgraph"):
            committee.deliberate(snapshot())

    def test_python_loop_is_the_default(self) -> None:
        assert DebateCommittee(analysts=default_analysts()).use_langgraph is False
