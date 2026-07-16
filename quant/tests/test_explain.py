from quantos.committee.committee import default_committee
from quantos.data.collector import synthetic_ohlcv
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import decision_report, explain_decision


def test_explain_decision_is_readable():
    df = synthetic_ohlcv("EX", "1h", 300, seed=20, trend=0.003, volatility=0.008)
    snap = MarketSnapshot(
        "EX", "1h", df,
        macro={"dxy_trend": -0.4, "risk_on": 0.6},
        sentiment={"score": 0.5},
        events={"FOMC": True},  # forces a visible veto in the report
    )
    decision = default_committee().deliberate(snap)
    text = explain_decision(decision)
    assert "DECISION" in text
    assert "ANALYST PANEL" in text
    assert "RISKS" in text
    assert "FOMC" in text  # veto surfaced


def test_decision_report_is_json_serialisable():
    import json

    df = synthetic_ohlcv("EX2", "1h", 200, seed=21)
    decision = default_committee().deliberate(MarketSnapshot("EX2", "1h", df))
    report = decision_report(decision)
    json.dumps(report, default=str)  # must not raise
    assert report["symbol"] == "EX2"
