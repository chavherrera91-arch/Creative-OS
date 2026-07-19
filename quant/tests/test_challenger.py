"""WP-6.4 — AI Challenger (devil's advocate, module 17).

Acceptance: a strong counter triggers exactly **one** extra deliberation
round and the decision explains the objection and whether it was decisive
(I4); a weak counter leaves the decision unchanged; the Challenger never
vetoes and cannot rescue or override the Risk Manager — the risk veto
remains absolute (I5). The rule challenger is deterministic (I8); the LLM
challenger fails safe on any malformed output (I3) and runs offline via the
mock only (I6).
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from conftest import make_ohlcv

from quantos.committee.base import Analyst, AnalystOpinion, Direction, Evidence
from quantos.committee.challenger import (
    Challenger,
    ChallengeResult,
    LLMChallenger,
    RuleChallenger,
)
from quantos.committee.debate import DebateCommittee
from quantos.committee.decision import CommitteeDecision
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import explain_decision
from quantos.llm.client import MockLLMClient


def snapshot(ohlcv: pd.DataFrame | None = None) -> MarketSnapshot:
    return MarketSnapshot("BTC/USDT", "1h", ohlcv if ohlcv is not None else make_ohlcv())


def decision(
    direction: Direction = Direction.LONG,
    approved: bool = True,
    blocked_by_risk: bool = False,
    opinions: list[AnalystOpinion] | None = None,
    regime: dict[str, Any] | None = None,
) -> CommitteeDecision:
    return CommitteeDecision(
        symbol="BTC/USDT",
        timeframe="1h",
        price=100.0,
        direction=direction,
        approved=approved,
        confidence=0.7,
        blocked_by_risk=blocked_by_risk,
        opinions=opinions or [],
        regime=regime or {},
    )


class CountingStub(Analyst):
    """A fixed LONG analyst that counts how often it is consulted."""

    def __init__(self, name: str, category: str) -> None:
        super().__init__(name=name, category=category)
        self.calls = 0

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        self.calls += 1
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.LONG,
            confidence=0.9,
            evidence=[Evidence(name="stub", detail="fixed LONG", impact=0.9)],
        )


class Caver(Analyst):
    """LONG until it sees a challenge in context — then it caves to FLAT."""

    def __init__(self) -> None:
        super().__init__(name="Caver", category="statistical")

    def analyze(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> AnalystOpinion:
        if context and "challenge" in context:
            return AnalystOpinion(
                analyst=self.name,
                category=self.category,
                direction=Direction.FLAT,
                confidence=0.1,
                evidence=[Evidence(name="cave", detail="the objection convinced me", impact=0.0)],
            )
        return AnalystOpinion(
            analyst=self.name,
            category=self.category,
            direction=Direction.LONG,
            confidence=0.9,
            evidence=[Evidence(name="conviction", detail="initial conviction", impact=0.9)],
        )


class AlwaysMaterial:
    """A challenger that always raises a material objection (test double)."""

    name = "Always Material"

    def contest(self, decision: CommitteeDecision, snapshot: MarketSnapshot) -> ChallengeResult:
        return ChallengeResult(
            agrees=False,
            material=True,
            argument="always contest",
            counter_evidence=[Evidence(name="always", detail="contrarian by design", impact=-0.9)],
            challenger=self.name,
        )


class ScriptedClient:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        self.calls += 1
        return self.payload


# ---------------------------------------------------------------------------
# RuleChallenger — deterministic devil's advocate
# ---------------------------------------------------------------------------


class TestRuleChallenger:
    def test_satisfies_the_port(self) -> None:
        assert isinstance(RuleChallenger(), Challenger)
        assert isinstance(LLMChallenger(MockLLMClient()), Challenger)

    def test_nothing_to_contest_when_standing_down(self) -> None:
        result = RuleChallenger().contest(
            decision(direction=Direction.FLAT, approved=False), snapshot()
        )
        assert result.agrees and not result.material
        assert "standing down" in result.argument

    def test_cannot_rescue_a_veto(self) -> None:
        """A vetoed decision is not contested — the veto is not the
        Challenger's to argue with (I5)."""
        vetoed = decision(direction=Direction.FLAT, approved=False, blocked_by_risk=True)
        result = RuleChallenger().contest(vetoed, snapshot())
        assert result.agrees and not result.material
        assert "vetoed" in result.argument

    def test_material_objection_on_a_stretched_long(self) -> None:
        """LONG into a +1.8σ, RSI~98 tape draws a strong counter-case."""
        stretched = snapshot(make_ohlcv(drift=0.004, vol=0.004, seed=7))
        result = RuleChallenger().contest(decision(), stretched)
        assert not result.agrees and result.material
        names = [e.name for e in result.counter_evidence]
        assert "overextension" in names and "rsi_extreme" in names
        assert all(e.impact < 0 for e in result.counter_evidence)  # against LONG
        json.dumps(result.as_dict())  # auditable (I4)
        replay = RuleChallenger().contest(decision(), stretched)
        assert replay.as_dict() == result.as_dict()  # deterministic (I8)

    def test_agrees_with_a_clean_call_on_a_calm_tape(self) -> None:
        result = RuleChallenger().contest(decision(), snapshot())
        assert result.agrees and not result.material
        assert result.counter_evidence == []

    def test_uses_the_committees_own_opposing_evidence(self) -> None:
        bearish = AnalystOpinion(
            analyst="Bear",
            category="macro",
            direction=Direction.SHORT,
            confidence=0.8,
            evidence=[Evidence(name="dxy", detail="dollar surging", impact=-0.8)],
        )
        result = RuleChallenger().contest(decision(opinions=[bearish]), snapshot())
        assert not result.agrees and result.material
        assert result.counter_evidence[0].name == "peer_dxy"
        assert "dollar surging" in result.counter_evidence[0].detail

    def test_regime_mismatch_counter(self) -> None:
        result = RuleChallenger().contest(
            decision(regime={"label": "TREND_DOWN", "tradeable": True}), snapshot()
        )
        assert not result.agrees and result.material
        assert result.counter_evidence[0].name == "regime_mismatch"
        assert result.counter_evidence[0].impact == -0.5


# ---------------------------------------------------------------------------
# LLMChallenger — fail-safe devil's advocate behind the LLMClient port
# ---------------------------------------------------------------------------


class TestLLMChallenger:
    def test_mock_contests_a_long_deterministically(self) -> None:
        result = LLMChallenger(MockLLMClient(seed=1)).contest(decision(), snapshot())
        assert not result.agrees and result.material
        assert all(e.impact < 0 for e in result.counter_evidence)
        replay = LLMChallenger(MockLLMClient(seed=1)).contest(decision(), snapshot())
        assert replay.as_dict() == result.as_dict()  # I8

    def test_fails_safe_on_malformed_output(self) -> None:
        """A broken challenger forces nothing (the I3 mirror)."""
        result = LLMChallenger(ScriptedClient("not json")).contest(decision(), snapshot())
        assert result.agrees and not result.material
        assert "failed safe" in result.argument

    def test_material_without_evidence_is_downgraded(self) -> None:
        payload = json.dumps(
            {"agrees": False, "material": True, "argument": "trust me", "counter_evidence": []}
        )
        result = LLMChallenger(ScriptedClient(payload)).contest(decision(), snapshot())
        assert not result.material
        assert "downgraded" in result.argument

    def test_supporting_impacts_are_dropped(self) -> None:
        """'Counter'-evidence that supports the call is nonsense: dropped."""
        payload = json.dumps(
            {
                "agrees": False,
                "material": True,
                "argument": "confused",
                "counter_evidence": [
                    {"name": "pro", "detail": "actually bullish", "impact": 0.9, "value": None}
                ],
            }
        )
        result = LLMChallenger(ScriptedClient(payload)).contest(decision(), snapshot())
        assert result.counter_evidence == []
        assert not result.material  # downgraded: nothing survived

    def test_unapproved_decision_skips_the_model(self) -> None:
        client = ScriptedClient("irrelevant")
        result = LLMChallenger(client).contest(decision(approved=False), snapshot())
        assert result.agrees and client.calls == 0


# ---------------------------------------------------------------------------
# Integration: the challenge step in the debate path
# ---------------------------------------------------------------------------


def bull_bench() -> list[CountingStub]:
    return [CountingStub("Bull-1", "technical"), CountingStub("Bull-2", "statistical")]


class TestDebateIntegration:
    def test_material_objection_triggers_exactly_one_extra_round(self) -> None:
        bench = bull_bench()
        committee = DebateCommittee(analysts=list(bench), challenger=AlwaysMaterial())
        final = committee.deliberate(snapshot())
        assert all(stub.calls == 3 for stub in bench)  # round 1 + revision + challenge round
        challenge = final.run_manifest["challenge"]
        assert challenge["extra_round"] is True
        assert challenge["decisive"] is False  # the bench did not budge
        assert challenge["provisional"] == {
            "direction": "LONG",
            "approved": True,
            "confidence": final.confidence,
        }
        # the challenger has NO veto: the unchanged conviction still trades (I5)
        assert final.approved and final.direction is Direction.LONG
        # ... and the objection is explained in the report (I4)
        assert "challenger objection was not decisive" in explain_decision(final)
        json.dumps(final.as_dict())

    def test_weak_counter_leaves_the_decision_unchanged(self) -> None:
        """A calm tape gives the RuleChallenger nothing material."""
        snap = snapshot()
        bench = bull_bench()
        plain = DebateCommittee(analysts=list(bull_bench())).deliberate(snap)
        committee = DebateCommittee(analysts=list(bench), challenger=RuleChallenger())
        final = committee.deliberate(snap)
        assert all(stub.calls == 2 for stub in bench)  # no extra round
        assert final.run_manifest["challenge"]["extra_round"] is False
        assert final.direction == plain.direction
        assert final.approved == plain.approved
        assert final.confidence == plain.confidence
        assert any("no material objection" in reason for reason in final.reasons)

    def test_decisive_objection_flips_the_outcome(self) -> None:
        committee = DebateCommittee(analysts=[Caver()], challenger=AlwaysMaterial())
        final = committee.deliberate(snapshot())
        assert not final.approved  # the re-round stood the committee down
        challenge = final.run_manifest["challenge"]
        assert challenge["decisive"] is True
        assert challenge["provisional"]["approved"] is True  # before the objection
        assert "challenger objection was DECISIVE" in explain_decision(final)

    def test_risk_veto_survives_any_challenge(self) -> None:
        """The veto is absolute in both directions (I5): the challenger can
        neither impose one nor argue one away."""
        committee = DebateCommittee(analysts=bull_bench(), challenger=AlwaysMaterial())
        final = committee.deliberate(snapshot(), context={"daily_pnl_pct": -0.10})
        assert final.blocked_by_risk
        assert final.direction is Direction.FLAT
        assert not final.approved
        # the rule challenger does not even contest a vetoed decision
        committee = DebateCommittee(analysts=bull_bench(), challenger=RuleChallenger())
        final = committee.deliberate(snapshot(), context={"daily_pnl_pct": -0.10})
        assert final.blocked_by_risk
        assert "nothing to contest" in final.run_manifest["challenge"]["argument"]

    def test_end_to_end_with_the_mock_llm_challenger(self) -> None:
        """Full offline loop: debate + LLM challenge + re-round (I6/I8)."""
        committee = DebateCommittee(
            analysts=bull_bench(), challenger=LLMChallenger(MockLLMClient(seed=9))
        )
        snap = snapshot()
        final = committee.deliberate(snap)
        assert final.run_manifest["challenge"]["extra_round"] is True
        assert final.approved and final.direction is Direction.LONG  # no veto power
        assert final.as_dict() == committee.deliberate(snap).as_dict()  # replays (I8)
