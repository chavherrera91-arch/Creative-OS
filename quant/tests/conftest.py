"""Shared fixtures for the quantos suite.

The whole suite runs offline, deterministically, with no network and no keys
(invariant I6). Fixtures added here are shared across all work packages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quantos.testing import assert_reproducible as _assert_reproducible

SEED = 42


@pytest.fixture()
def seed() -> int:
    """The canonical test seed (I8)."""
    return SEED


@pytest.fixture()
def assert_reproducible() -> Callable[..., Any]:
    """Helper asserting that a research function replays identically (I8)."""
    return _assert_reproducible


def make_ohlcv(
    n: int = 200,
    seed: int = SEED,
    drift: float = 0.0,
    vol: float = 0.01,
    start: str = "2024-01-01",
    freq: str = "1h",
) -> pd.DataFrame:
    """Deterministic random-walk OHLCV frame for tests (no network, I6)."""
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(drift, vol, size=n)
    close = 100.0 * np.exp(np.cumsum(log_ret))
    open_ = np.concatenate([[100.0], close[:-1]])
    spread = np.abs(rng.normal(0.0, vol / 2.0, size=n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.uniform(50.0, 150.0, size=n)
    index = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


@pytest.fixture()
def ohlcv() -> pd.DataFrame:
    """A neutral random-walk OHLCV fixture."""
    return make_ohlcv()


@pytest.fixture()
def uptrend_ohlcv() -> pd.DataFrame:
    """A strongly trending-up OHLCV fixture."""
    return make_ohlcv(drift=0.004, vol=0.004, seed=7)


@pytest.fixture()
def downtrend_ohlcv() -> pd.DataFrame:
    """A strongly trending-down OHLCV fixture."""
    return make_ohlcv(drift=-0.004, vol=0.004, seed=7)
