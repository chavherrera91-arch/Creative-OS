import pandas as pd

from quantos.committee.base import AnalystOpinion, Direction, Evidence
from quantos.committee.chair import Chair
from quantos.committee.confidence import ConfidenceModel
from quantos.committee.risk_manager import RiskManager
from quantos.config import RiskConfig
from quantos.data.collector import synthetic_ohlcv
from quantos.data.models import MarketSnapshot


def _op(cat, direction, conf, abstained=False):
    return AnalystOpinion("A", cat, direction, conf, [Evidence("e", "d", 0.1)], abstained)


def test_confidence_aggregates_agreement():
    model = ConfidenceModel(confidence_threshold=0.5, agreement_threshold=0.5)
    ops = [
        _op("technical", Direction.LONG, 0.9),
        _op("statistical", Direction.LONG, 0.8),
        _op("macro", Direction.SHORT, 0.2),
    ]
    report = model.aggregate(ops)
    assert report.direction is Direction.LONG
    assert report.meets_threshold
    assert 0 < report.agreement <= 1


def test_confidence_below_threshold_does_not_trade():
    model = ConfidenceModel(confidence_threshold=0.8, agreement_threshold=0.5)
    ops = [_op("technical", Direction.LONG, 0.3), _op("macro", Direction.SHORT, 0.25)]
    report = model.aggregate(ops)
    assert not report.meets_threshold


def test_all_abstain_yields_flat():
    model = ConfidenceModel()
    report = model.aggregate([_op("macro", Direction.FLAT, 0.0, abstained=True)])
    assert report.direction is Direction.FLAT
    assert report.participants == 0


def test_risk_manager_vetoes_on_event():
    df = synthetic_ohlcv("R", "1h", 200, seed=3)
    snap = MarketSnapshot("R", "1h", df, events={"FOMC": True})
    assessment = RiskManager().assess(snap)
    assert not assessment.approved
    assert any("FOMC" in v for v in assessment.vetoes)


def test_risk_manager_vetoes_on_drawdown():
    df = synthetic_ohlcv("R", "1h", 200, seed=4)
    snap = MarketSnapshot("R", "1h", df)
    assessment = RiskManager(RiskConfig(max_daily_drawdown=0.02)).assess(
        snap, {"daily_drawdown": -0.05}
    )
    assert not assessment.approved


def test_veto_overrides_bullish_confidence():
    """Even a unanimous LONG must be blocked by a risk veto."""
    from quantos.committee.risk_manager import RiskAssessment

    df = synthetic_ohlcv("R", "1h", 200, seed=6)
    snap = MarketSnapshot("R", "1h", df)
    ops = [_op("technical", Direction.LONG, 0.95), _op("statistical", Direction.LONG, 0.95)]
    report = ConfidenceModel(confidence_threshold=0.5, agreement_threshold=0.5).aggregate(ops)
    assert report.meets_threshold  # committee wanted to trade
    blocked = RiskAssessment(approved=False, vetoes=["Imminent macro event: FOMC"])
    decision = Chair().decide(snap, ops, report, blocked)
    assert decision.blocked_by_risk
    assert decision.direction is Direction.FLAT
    assert not decision.approved
