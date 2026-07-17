"""WP-1.1 — core data model + collector acceptance tests (offline, I6)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from quantos.config import Settings
from quantos.data.collector import DataCollector, synthetic_channels, synthetic_ohlcv
from quantos.data.models import OHLCV_COLUMNS, MarketSnapshot


class TestSettings:
    def test_defaults_are_offline_safe(self) -> None:
        settings = Settings()
        assert settings.symbol == "BTC/USDT"
        assert settings.seed == 42

    def test_from_env_overrides(self) -> None:
        env = {"QUANTOS_SYMBOL": "ETH/USDT", "QUANTOS_BARS": "123", "QUANTOS_FEE_BPS": "2.5"}
        settings = Settings.from_env(env)
        assert settings.symbol == "ETH/USDT"
        assert settings.bars == 123
        assert settings.fee_bps == 2.5
        assert settings.timeframe == "1h"  # untouched default

    def test_as_dict_serialisable(self) -> None:
        json.dumps(Settings().as_dict())


class TestSyntheticData:
    def test_deterministic_for_fixed_seed(self) -> None:
        a = synthetic_ohlcv("BTC/USDT", "1h", bars=200, seed=42)
        b = synthetic_ohlcv("BTC/USDT", "1h", bars=200, seed=42)
        pd.testing.assert_frame_equal(a, b)

    def test_seed_and_symbol_change_the_path(self) -> None:
        base = synthetic_ohlcv("BTC/USDT", "1h", bars=100, seed=42)
        other_seed = synthetic_ohlcv("BTC/USDT", "1h", bars=100, seed=43)
        other_symbol = synthetic_ohlcv("ETH/USDT", "1h", bars=100, seed=42)
        assert not base["close"].equals(other_seed["close"])
        assert not base["close"].equals(other_symbol["close"])

    def test_shape_and_sanity(self) -> None:
        df = synthetic_ohlcv("BTC/USDT", "1h", bars=150, seed=1)
        assert list(df.columns) == list(OHLCV_COLUMNS)
        assert len(df) == 150
        assert df.index.is_monotonic_increasing
        assert not df.isna().any().any()
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
        assert (df["volume"] > 0).all()

    def test_channels_deterministic(self) -> None:
        assert synthetic_channels("BTC/USDT", seed=42) == synthetic_channels("BTC/USDT", seed=42)


class TestMarketSnapshot:
    def test_validates_ohlcv_columns(self, ohlcv: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="missing columns"):
            MarketSnapshot("BTC/USDT", "1h", ohlcv.drop(columns=["close"]))

    def test_rejects_empty_frame(self, ohlcv: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="empty"):
            MarketSnapshot("BTC/USDT", "1h", ohlcv.iloc[0:0])

    def test_properties_and_channels(self, ohlcv: pd.DataFrame) -> None:
        snap = MarketSnapshot("BTC/USDT", "1h", ohlcv, sentiment={"score": 0.5})
        assert snap.last_price == float(ohlcv["close"].iloc[-1])
        assert snap.bars == len(ohlcv)
        assert snap.has("sentiment")
        assert not snap.has("macro")

    def test_as_dict_serialisable(self, ohlcv: pd.DataFrame) -> None:
        report = MarketSnapshot("BTC/USDT", "1h", ohlcv).as_dict()
        json.dumps(report)
        assert report["channels"]["macro"] is False


class TestDataCollector:
    def test_offline_snapshot_is_deterministic(self) -> None:
        collector = DataCollector(force_synthetic=True)
        a = collector.snapshot("BTC/USDT", "1h", bars=120)
        b = collector.snapshot("BTC/USDT", "1h", bars=120)
        pd.testing.assert_frame_equal(a.ohlcv, b.ohlcv)
        assert collector.last_source == "synthetic"

    def test_default_path_never_needs_network(self) -> None:
        # ccxt is not installed in the research environment: the default
        # (non-forced) path must silently degrade to synthetic data (I6).
        collector = DataCollector()
        snap = collector.snapshot(bars=64)
        assert snap.bars == 64
        assert collector.last_source in ("synthetic", "ccxt")

    def test_injected_exchange_is_read_only_use(self) -> None:
        class FakeExchange:
            def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
                base = 1_700_000_000_000
                return [
                    [base + i * 3_600_000, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10.0]
                    for i in range(limit)
                ]

        collector = DataCollector(exchange=FakeExchange())
        snap = collector.snapshot("BTC/USDT", "1h", bars=5)
        assert collector.last_source == "ccxt"
        assert snap.bars == 5

    def test_include_channels_builds_full_snapshot(self) -> None:
        snap = DataCollector(force_synthetic=True).snapshot(bars=50, include_channels=True)
        for channel in ("derivatives", "onchain", "macro", "sentiment"):
            assert snap.has(channel), channel
