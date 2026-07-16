from quantos.data.collector import DataCollector, synthetic_ohlcv
from quantos.data.models import OHLCV_COLUMNS, MarketSnapshot


def test_synthetic_is_deterministic():
    a = synthetic_ohlcv("BTC/USDT", "1h", 100)
    b = synthetic_ohlcv("BTC/USDT", "1h", 100)
    assert a["close"].equals(b["close"])


def test_synthetic_columns_and_length():
    df = synthetic_ohlcv("X", "15m", 250)
    assert list(df.columns) == list(OHLCV_COLUMNS)
    assert len(df) == 250
    # High >= low, high >= close, etc.
    assert (df["high"] >= df["low"]).all()


def test_trend_direction():
    up = synthetic_ohlcv("U", "1h", 300, seed=5, trend=0.005, volatility=0.005)
    assert up["close"].iloc[-1] > up["close"].iloc[0]


def test_collector_snapshot_offline():
    snap = DataCollector(source="synthetic").snapshot("ETH/USDT", "1h", 120)
    assert isinstance(snap, MarketSnapshot)
    assert snap.symbol == "ETH/USDT"
    assert snap.last_price > 0


def test_snapshot_requires_ohlcv_columns():
    import pandas as pd
    import pytest

    with pytest.raises(ValueError):
        MarketSnapshot("BAD", "1h", pd.DataFrame({"close": [1, 2, 3]}))
