from quantos.committee.analysts import TechnicalAnalyst
from quantos.committee.base import Direction
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.data.collector import synthetic_ohlcv
from quantos.data.models import MarketSnapshot


def test_technical_analyst_bullish_on_uptrend(bull_snapshot):
    op = TechnicalAnalyst().analyze(bull_snapshot)
    assert op.direction is Direction.LONG
    assert op.confidence > 0
    assert op.evidence  # must justify itself


def test_technical_analyst_abstains_without_history():
    df = synthetic_ohlcv("S", "1h", 10)
    op = TechnicalAnalyst().analyze(MarketSnapshot("S", "1h", df))
    assert op.abstained


def test_committee_reaches_decision(bull_snapshot):
    decision = default_committee().deliberate(bull_snapshot)
    assert decision.symbol == "TEST/UP"
    assert decision.opinions
    # An uptrend should at least lean long in the proposal.
    assert decision.proposed_direction in (Direction.LONG, Direction.FLAT)


def test_missing_channels_abstain_but_committee_still_decides(bull_snapshot):
    decision = default_committee().deliberate(bull_snapshot)
    # macro/sentiment/onchain have no data -> they abstain
    assert decision.confidence_report.abstentions >= 3
    assert decision.confidence_report.participants >= 1


def test_side_channels_are_used():
    df = synthetic_ohlcv("C", "1h", 300, seed=9, trend=0.003, volatility=0.008)
    snap = MarketSnapshot(
        "C", "1h", df,
        macro={"dxy_trend": -0.5, "rate_bias": -0.5, "risk_on": 0.8},
        sentiment={"score": 0.7},
        onchain={"net_exchange_flow": -0.6, "whale_accumulation": 0.7},
    )
    decision = default_committee().deliberate(snap)
    assert decision.confidence_report.participants == 5
    assert decision.confidence_report.abstentions == 0


def test_empty_committee_stands_down(bull_snapshot):
    committee = InvestmentCommittee(analysts=[])
    decision = committee.deliberate(bull_snapshot)
    assert decision.direction is Direction.FLAT
    assert not decision.approved
