"""WP-9.3 — Meta-Risk: audit the Risk Manager from history, propose only (I8)."""

from __future__ import annotations

from quantos.memory import DecisionArchive
from quantos.risk.meta import MetaRisk


def record(
    did_seed: str,
    *,
    blocked: bool,
    regime: str = "TREND_UP",
    direction: str = "LONG",
) -> dict:
    """A minimal archived-decision dict (unique via the reasons seed)."""
    return {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "price": 100.0,
        "direction": direction,
        "approved": not blocked,
        "confidence": 0.8,
        "blocked_by_risk": blocked,
        "reasons": [did_seed],
        "opinions": [],
        "regime": {"label": regime},
        "strategies_considered": [],
        "run_manifest": {"seed": 1},
        "as_of": "2024-02-01T00:00:00+00:00",
    }


def archive_with(blocked_pnls: list[float], allowed_pnls: list[float]) -> DecisionArchive:
    archive = DecisionArchive()
    for i, pnl in enumerate(blocked_pnls):
        did = archive.record(record(f"blocked-{i}", blocked=True))
        archive.record_outcome(did, pnl=pnl, notes="counterfactual")
    for i, pnl in enumerate(allowed_pnls):
        did = archive.record(record(f"allowed-{i}", blocked=False))
        archive.record_outcome(did, pnl=pnl)
    return archive


class TestMetaRisk:
    def test_flags_over_blocking_and_proposes_relaxation(self) -> None:
        # Vetoes blocked mostly-winning setups → over-blocking.
        archive = archive_with(blocked_pnls=[50.0, 40.0, 60.0, -10.0], allowed_pnls=[20.0])
        report = MetaRisk().assess(archive)
        assert report.overall.blocked_win_rate >= 0.6
        assert report.over_blocking
        assert any(p["kind"] == "relax_limits" for p in report.proposals)

    def test_proposes_tightening_when_allowed_setups_lose(self) -> None:
        archive = archive_with(blocked_pnls=[-30.0], allowed_pnls=[-10.0, -20.0, -5.0, -8.0])
        report = MetaRisk().assess(archive)
        assert any(p["kind"] == "tighten_limits" for p in report.proposals)

    def test_no_proposal_below_min_samples(self) -> None:
        archive = archive_with(blocked_pnls=[50.0], allowed_pnls=[10.0])
        report = MetaRisk(min_samples=3).assess(archive)
        assert report.proposals == []

    def test_regime_specific_relaxation(self) -> None:
        archive = DecisionArchive()
        for i in range(4):
            did = archive.record(record(f"crisis-{i}", blocked=True, regime="CRISIS"))
            archive.record_outcome(did, pnl=30.0)
        report = MetaRisk().assess(archive)
        regime_props = [p for p in report.proposals if p.get("scope") == "regime"]
        assert regime_props and regime_props[0]["regime"] == "CRISIS"

    def test_is_deterministic_and_serialisable(self) -> None:
        import json

        archive = archive_with(blocked_pnls=[50.0, 40.0, 60.0], allowed_pnls=[10.0])
        first = MetaRisk().assess(archive).as_dict()
        second = MetaRisk().assess(archive).as_dict()
        assert first == second
        json.dumps(first)

    def test_never_mutates_limits(self) -> None:
        # Meta-Risk only proposes: it exposes no apply/mutate path (§4.1).
        engine = MetaRisk()
        for attribute in ("apply", "set_limit", "update_limits", "mutate"):
            assert not hasattr(engine, attribute)
