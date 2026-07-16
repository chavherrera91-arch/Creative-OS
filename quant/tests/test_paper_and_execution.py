import pytest

from quantos.committee.base import Direction
from quantos.committee.committee import default_committee
from quantos.data.collector import synthetic_ohlcv
from quantos.data.models import MarketSnapshot
from quantos.execution.interfaces import (
    Broker,
    LiveExecutionDisabled,
    PaperExecutionEngine,
    build_execution_engine,
)
from quantos.paper.broker import PaperBroker


def test_paper_broker_buy_updates_position_and_cash():
    broker = PaperBroker(cash=1000.0, fee_rate=0.0, slippage=0.0)
    broker.submit("BTC/USDT", "buy", 2.0, 100.0)
    assert broker.position == 2.0
    assert broker.cash == pytest.approx(800.0)
    assert broker.equity(100.0) == pytest.approx(1000.0)


def test_paper_broker_records_trade_dossier():
    broker = PaperBroker()
    rec = broker.submit("BTC/USDT", "buy", 1.0, 100.0, reason="committee LONG", context={"c": 0.9})
    assert rec.reason == "committee LONG"
    assert broker.blotter()[0]["symbol"] == "BTC/USDT"


def test_paper_broker_target_position():
    broker = PaperBroker(fee_rate=0.0, slippage=0.0)
    broker.target_position("X", 3.0, 10.0)
    assert broker.position == 3.0
    broker.target_position("X", -1.0, 10.0)  # flip to short
    assert broker.position == -1.0


def test_paper_broker_satisfies_broker_protocol():
    assert isinstance(PaperBroker(), Broker)


def test_execution_engine_refuses_live():
    with pytest.raises(LiveExecutionDisabled):
        build_execution_engine(PaperBroker(), live=True)


def test_execution_engine_paper_ok():
    engine = build_execution_engine(PaperBroker(), live=False)
    assert isinstance(engine, PaperExecutionEngine)


def test_execution_engine_rejects_non_paper_broker():
    class FakeLiveBroker:
        is_paper = False

        def submit(self, *a, **k):  # pragma: no cover
            raise AssertionError("must never be called")

        def equity(self, mark_price):  # pragma: no cover
            return 0.0

    with pytest.raises(LiveExecutionDisabled):
        PaperExecutionEngine(FakeLiveBroker())


def test_execution_engine_only_acts_on_approved_decisions():
    df = synthetic_ohlcv("E", "1h", 300, seed=15, trend=0.003, volatility=0.008)
    snap = MarketSnapshot("E", "1h", df)
    decision = default_committee().deliberate(snap)
    broker = PaperBroker()
    engine = build_execution_engine(broker)
    engine.execute(decision, snap.last_price)
    if decision.approved and decision.direction is not Direction.FLAT:
        assert len(broker.trades) == 1
    else:
        assert len(broker.trades) == 0
