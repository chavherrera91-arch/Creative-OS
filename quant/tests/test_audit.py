"""WP-7.5 — the Auditor: mine closed trades, identify the weak link, propose."""

from __future__ import annotations

from quantos.learning import audit
from quantos.memory import DecisionArchive
from tests.test_archive import fake_record


def opinion(analyst: str, category: str, direction: str, abstained: bool = False) -> dict:
    return {
        "analyst": analyst,
        "category": category,
        "direction": direction,
        "confidence": 0.8,
        "abstained": abstained,
        "evidence": [],
    }


def seeded_archive() -> DecisionArchive:
    """Technical is always right; Macro is always wrong; On-chain abstains."""
    archive = DecisionArchive()
    outcomes = [(True, 10.0), (False, -8.0), (True, 6.0), (False, -4.0)]
    for i, (win, pnl) in enumerate(outcomes):
        record = fake_record(as_of=f"2024-01-{10 + i:02d}T00:00:00+00:00", regime="TREND_UP")
        record["direction"] = "LONG"
        record["opinions"] = [
            # right: agrees with winners, dissents from losers
            opinion("Technical Analyst", "technical", "LONG" if win else "SHORT"),
            # wrong: dissents from winners, agrees with losers
            opinion("Macro Analyst", "macro", "SHORT" if win else "LONG"),
            # honest abstention — must never be scored (I3)
            opinion("On-chain Analyst", "onchain", "FLAT", abstained=True),
        ]
        record["strategies_considered"] = [{"family": "trend", "name": f"s{i}"}]
        archive.record_outcome(archive.record(record), pnl=pnl)
    return archive


class TestScoring:
    def test_identifies_the_bad_analyst(self) -> None:
        report = audit(seeded_archive())
        assert report.n_closed == 4
        worst = report.worst_analyst
        assert worst is not None and worst.analyst == "Macro Analyst"
        assert worst.hit_rate == 0.0
        best = {a.analyst: a for a in report.analysts}["Technical Analyst"]
        assert best.hit_rate == 1.0

    def test_abstentions_are_never_scored(self) -> None:
        report = audit(seeded_archive())
        assert all(a.analyst != "On-chain Analyst" for a in report.analysts)  # I3

    def test_regime_and_family_breakdowns(self) -> None:
        report = audit(seeded_archive())
        assert report.regimes["TREND_UP"]["n"] == 4.0
        assert report.families["trend@TREND_UP"]["n"] == 4.0


class TestProposals:
    def test_proposes_lowering_the_bad_analysts_weight(self) -> None:
        report = audit(seeded_archive())
        weight_proposals = [p for p in report.proposals if p["kind"] == "analyst_weight"]
        assert len(weight_proposals) == 1
        proposal = weight_proposals[0]
        assert proposal["target"] == "macro" and proposal["analyst"] == "Macro Analyst"
        assert proposal["proposed"] < proposal["current"]  # lower, never raise here

    def test_proposes_revoking_a_losing_family(self) -> None:
        report = audit(seeded_archive())  # mean pnl over the four trades is +1.0
        assert not any(p["kind"] == "meta_validation" for p in report.proposals)
        archive = seeded_archive()
        for i in range(3):  # add three more losers to sink the family mean
            record = fake_record(as_of=f"2024-02-{10 + i:02d}T00:00:00+00:00", regime="TREND_UP")
            record["strategies_considered"] = [{"family": "trend", "name": f"x{i}"}]
            archive.record_outcome(archive.record(record), pnl=-20.0)
        revoke = [p for p in audit(archive).proposals if p["kind"] == "meta_validation"]
        assert len(revoke) == 1 and revoke[0]["target"] == "trend"

    def test_report_is_deterministic_and_serialisable(self) -> None:
        import json

        first = audit(seeded_archive()).as_dict()
        second = audit(seeded_archive()).as_dict()
        assert first == second  # I8
        json.dumps(first)

    def test_min_samples_gate_holds_proposals_back(self) -> None:
        archive = DecisionArchive()
        record = fake_record()
        record["opinions"] = [opinion("Macro Analyst", "macro", "SHORT")]
        archive.record_outcome(archive.record(record), pnl=5.0)  # one wrong call only
        assert audit(archive, min_samples=3).proposals == []
