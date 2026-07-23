"""WP-9.4 — Self-Evaluation: rank decaying analysts & signals from history (I8)."""

from __future__ import annotations

from quantos.learning import SelfEvaluator
from quantos.memory import DecisionArchive


def decision(
    seed: str,
    as_of: str,
    *,
    macro_dir: str,
    onchain_dir: str,
    rsi_impact: float,
    whale_impact: float,
) -> dict:
    """A record with a Macro analyst (via rsi) and an Onchain analyst (via whale)."""
    return {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "price": 100.0,
        "direction": "LONG",
        "approved": True,
        "confidence": 0.7,
        "blocked_by_risk": False,
        "reasons": [seed],
        "opinions": [
            {
                "analyst": "Macro",
                "direction": macro_dir,
                "abstained": False,
                "evidence": [{"name": "rsi", "impact": rsi_impact}],
            },
            {
                "analyst": "Onchain",
                "direction": onchain_dir,
                "abstained": False,
                "evidence": [{"name": "whale", "impact": whale_impact}],
            },
        ],
        "regime": {"label": "TREND_UP"},
        "run_manifest": {"seed": 1},
        "as_of": as_of,
    }


def decaying_archive() -> DecisionArchive:
    """Macro & rsi were right early and wrong recently; Onchain & whale stay right."""
    archive = DecisionArchive()
    # Earlier window: LONG calls that won — Macro/rsi agree and are right.
    for i in range(2):
        rec = decision(
            f"early-{i}",
            f"2024-01-0{i + 1}T00:00:00+00:00",
            macro_dir="LONG",
            onchain_dir="LONG",
            rsi_impact=0.5,
            whale_impact=0.5,
        )
        did = archive.record(rec)
        archive.record_outcome(did, pnl=50.0)
    # Recent window: LONG calls that lost — Macro/rsi still bullish (now wrong);
    # Onchain/whale flipped bearish (dissent from a losing call = right).
    for i in range(2):
        rec = decision(
            f"late-{i}",
            f"2024-03-0{i + 1}T00:00:00+00:00",
            macro_dir="LONG",
            onchain_dir="SHORT",
            rsi_impact=0.5,
            whale_impact=-0.5,
        )
        did = archive.record(rec)
        archive.record_outcome(did, pnl=-50.0)
    return archive


class TestSelfEvaluator:
    def test_ranks_the_decaying_analyst_and_signal(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        degrading = {i.name for i in report.degrading}
        assert "Macro" in degrading  # analyst lost its edge
        assert "rsi" in degrading  # indicator lost predictive power

    def test_stable_components_are_not_flagged(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        degrading = {i.name for i in report.degrading}
        assert "Onchain" not in degrading
        assert "whale" not in degrading

    def test_delta_direction_and_least_useful(self) -> None:
        report = SelfEvaluator().evaluate(decaying_archive())
        macro = next(i for i in report.analysts if i.name == "Macro")
        assert macro.earlier_hit == 1.0 and macro.recent_hit == 0.0
        assert report.least_useful_analyst is not None
        assert report.least_useful_analyst.name == "Macro"

    def test_is_deterministic_and_serialisable(self) -> None:
        import json

        first = SelfEvaluator().evaluate(decaying_archive()).as_dict()
        second = SelfEvaluator().evaluate(decaying_archive()).as_dict()
        assert first == second
        json.dumps(first)

    def test_empty_archive_is_safe(self) -> None:
        report = SelfEvaluator().evaluate(DecisionArchive())
        assert report.n_closed == 0
        assert report.degrading == []

    def test_stale_datasets_from_health(self) -> None:
        health = {
            "sentiment": {"success_rate": 0.2},
            "market": {"success_rate": 0.99},
        }
        report = SelfEvaluator().evaluate(decaying_archive(), health=health)
        assert any("sentiment" in d for d in report.datasets)
        assert not any("market" in d for d in report.datasets)

    def test_only_reports_no_mutation_path(self) -> None:
        evaluator = SelfEvaluator()
        for attribute in ("apply", "fix", "retrain", "mutate"):
            assert not hasattr(evaluator, attribute)
