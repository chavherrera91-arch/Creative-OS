"""Shared fixtures. All synthetic — no network, no keys."""

from __future__ import annotations

import pytest

from quantos.data.collector import synthetic_ohlcv
from quantos.data.models import MarketSnapshot


@pytest.fixture
def bull_ohlcv():
    return synthetic_ohlcv("TEST/UP", "1h", 400, seed=1, trend=0.004, volatility=0.01)


@pytest.fixture
def bear_ohlcv():
    return synthetic_ohlcv("TEST/DN", "1h", 400, seed=2, trend=-0.004, volatility=0.01)


@pytest.fixture
def bull_snapshot(bull_ohlcv):
    return MarketSnapshot("TEST/UP", "1h", bull_ohlcv)
