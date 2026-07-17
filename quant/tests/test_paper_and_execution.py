"""WP-1.8 — paper broker, hard-disabled live execution (I1), CLI."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from quantos.committee.committee import default_committee
from quantos.data.models import MarketSnapshot
from quantos.execution.interfaces import (
    DefaultRiskGate,
    LiveExecutionDisabled,
    PaperExecutionEngine,
    build_execution_engine,
)
from quantos.paper.broker import PaperBroker


def bullish_snapshot(ohlcv: pd.DataFrame, **overrides: object) -> MarketSnapshot:
    channels: dict[str, object] = {
        "macro": {"dxy_trend": -0.9, "risk_appetite": 0.9},
        "sentiment": {"score": 0.6},
        "onchain": {"whale_accumulation": 0.8},
    }
    channels.update(overrides)
    return MarketSnapshot("BTC/USDT", "1h", ohlcv, **channels)  # type: ignore[arg-type]


class TestPaperBroker:
    def test_buy_sell_round_trip_costs_money(self) -> None:
        broker = PaperBroker(cash=10_000.0, fee_bps=10, slippage_bps=5)
        broker.submit("BTC/USDT", "buy", qty=0.1, price=50_000.0)
        assert broker.position("BTC/USDT") == pytest.approx(0.1)
        broker.submit("BTC/USDT", "sell", qty=0.1, price=50_000.0)
        assert broker.position("BTC/USDT") == pytest.approx(0.0)
        # fees + adverse slippage make the round trip strictly negative
        assert broker.cash < 10_000.0

    def test_slippage_is_always_adverse(self) -> None:
        broker = PaperBroker(slippage_bps=10)
        buy = broker.submit("BTC/USDT", "buy", qty=1.0, price=100.0)
        sell = broker.submit("BTC/USDT", "sell", qty=1.0, price=100.0)
        assert buy.fill_price > 100.0
        assert sell.fill_price < 100.0

    def test_trade_record_carries_dossier(self) -> None:
        broker = PaperBroker()
        record = broker.submit(
            "BTC/USDT", "buy", qty=1.0, price=100.0, as_of="2024-01-01", dossier={"reasons": ["x"]}
        )
        assert record.dossier == {"reasons": ["x"]}
        assert record.as_of == "2024-01-01"
        json.dumps(record.as_dict())

    def test_rejects_invalid_orders(self) -> None:
        broker = PaperBroker()
        with pytest.raises(ValueError):
            broker.submit("BTC/USDT", "hold", qty=1.0, price=100.0)
        with pytest.raises(ValueError):
            broker.submit("BTC/USDT", "buy", qty=-1.0, price=100.0)
        with pytest.raises(ValueError):
            broker.submit("BTC/USDT", "buy", qty=1.0, price=0.0)

    def test_is_paper_flag(self) -> None:
        assert PaperBroker.is_paper is True


class TestLiveExecutionIsDisabled:
    """I1 guard tests — these must never be weakened."""

    def test_build_engine_live_true_raises(self) -> None:
        with pytest.raises(LiveExecutionDisabled):
            build_execution_engine(live=True)

    def test_non_paper_broker_is_rejected(self) -> None:
        class SneakyLiveBroker:
            is_paper = False

            def submit(self, *a: object, **k: object) -> None:  # pragma: no cover
                raise AssertionError("must never be reached")

            def equity(self, prices: object = None) -> float:
                return 0.0

        with pytest.raises(LiveExecutionDisabled):
            PaperExecutionEngine(broker=SneakyLiveBroker())  # type: ignore[arg-type]
        with pytest.raises(LiveExecutionDisabled):
            build_execution_engine(broker=SneakyLiveBroker())  # type: ignore[arg-type]

    def test_missing_is_paper_flag_is_rejected(self) -> None:
        class FlaglessBroker:
            def submit(self, *a: object, **k: object) -> None:  # pragma: no cover
                raise AssertionError("must never be reached")

            def equity(self, prices: object = None) -> float:
                return 0.0

        with pytest.raises(LiveExecutionDisabled):
            build_execution_engine(broker=FlaglessBroker())  # type: ignore[arg-type]


class TestPaperExecutionEngine:
    def test_approved_decision_produces_trade_with_dossier(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        assert decision.approved
        engine = build_execution_engine()
        record = engine.execute(decision)
        assert record is not None
        assert record.qty > 0
        assert record.side == "buy"
        assert record.dossier["symbol"] == "BTC/USDT"
        assert record.dossier["reasons"]  # the full decision record rides along (I4)

    def test_vetoed_decision_is_not_executed(self, uptrend_ohlcv: pd.DataFrame) -> None:
        snap = bullish_snapshot(uptrend_ohlcv, events=[{"name": "FOMC", "impact": "high"}])
        decision = default_committee().deliberate(snap)
        assert decision.blocked_by_risk
        engine = build_execution_engine()
        assert engine.execute(decision) is None
        assert not engine.broker.trades  # type: ignore[attr-defined]

    def test_stand_down_is_not_executed(self, ohlcv: pd.DataFrame) -> None:
        committee = default_committee()
        committee.confidence_model.threshold = 0.99
        decision = committee.deliberate(bullish_snapshot(ohlcv))
        assert build_execution_engine().execute(decision) is None

    def test_position_size_is_bounded(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        engine = PaperExecutionEngine()
        record = engine.execute(decision)
        assert record is not None
        max_notional = 100_000.0 * engine.settings.max_position_fraction
        assert record.notional <= max_notional * 1.01

    def test_default_risk_gate(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        assert DefaultRiskGate().allow(decision)
        decision.approved = False
        assert not DefaultRiskGate().allow(decision)


class TestCLI:
    def test_decide_prints_full_explanation(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        assert main(["decide", "--bars", "200", "--synthetic"]) == 0
        out = capsys.readouterr().out
        assert "INVESTMENT COMMITTEE — DECISION REPORT" in out
        assert "ANALYST PANEL" in out
        assert "CHAIR" in out

    def test_decide_is_reproducible(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        main(["decide", "--bars", "200", "--synthetic", "--seed", "5"])
        first = capsys.readouterr().out
        main(["decide", "--bars", "200", "--synthetic", "--seed", "5"])
        second = capsys.readouterr().out
        assert first == second  # I8

    def test_backtest_reports_baselines(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        assert main(["backtest", "--bars", "150", "--synthetic", "--step", "15"]) == 0
        out = capsys.readouterr().out
        assert "buy_and_hold" in out
        assert "beats_random" in out

    def test_walkforward_smoke(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        code = main(
            [
                "walkforward",
                "--bars",
                "220",
                "--synthetic",
                "--folds",
                "2",
                "--min-train",
                "100",
                "--step",
                "20",
            ]
        )
        assert code == 0
        assert "out-of-sample" in capsys.readouterr().out

    def test_montecarlo_smoke(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        assert (
            main(["montecarlo", "--bars", "150", "--synthetic", "--sims", "50", "--step", "15"])
            == 0
        )
        assert "total_return_percentiles" in capsys.readouterr().out

    def test_paper_smoke(self, capsys: pytest.CaptureFixture[str]) -> None:
        from quantos.cli import main

        assert main(["paper", "--bars", "200", "--synthetic", "--channels"]) == 0
        out = capsys.readouterr().out
        assert "PAPER" in out  # either a trade record or an explicit no-trade line
