"""Property-based tests for the hard invariants (ARCHITECTURE §9.1).

I2 (no look-ahead) and I8 (reproducibility) are asserted over *generated*
inputs, not a single fixture. ``hypothesis`` is optional (extra ``[dev]``):
without it the property tests skip and the deterministic checks still run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.backtest.baselines import vs_baselines
from quantos.testing import assert_reproducible

try:  # hypothesis is an optional dev dependency — guard the import (I6).
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover - exercised on minimal installs
    HAS_HYPOTHESIS = False

requires_hypothesis = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")


# ---------------------------------------------------------------------------
# Deterministic scaffold checks (always run)
# ---------------------------------------------------------------------------


def test_assert_reproducible_accepts_deterministic_fn() -> None:
    def fn() -> dict[str, object]:
        rng = np.random.default_rng(123)
        return {"x": rng.normal(size=5), "s": pd.Series([1.0, 2.0])}

    assert_reproducible(fn)


def test_assert_reproducible_rejects_nondeterministic_fn() -> None:
    counter = iter(range(100))

    def fn() -> int:
        return next(counter)

    with pytest.raises(AssertionError):
        assert_reproducible(fn)


def test_vs_baselines_reports_both_benchmarks() -> None:
    df = make_ohlcv(n=300)
    returns = df["close"].pct_change().fillna(0.0) * 0.5
    report = vs_baselines(returns, df["close"])
    assert set(report) >= {
        "strategy",
        "buy_and_hold",
        "random",
        "beats_buy_and_hold",
        "beats_random",
    }
    for key in ("strategy", "buy_and_hold", "random"):
        metrics = report[key]
        assert isinstance(metrics, dict) and "sharpe" in metrics


def test_vs_baselines_is_deterministic() -> None:
    df = make_ohlcv(n=200)
    returns = df["close"].pct_change().fillna(0.0)
    assert_reproducible(vs_baselines, returns, df["close"], seed=11)


# ---------------------------------------------------------------------------
# Property tests (run when hypothesis is installed, e.g. in CI)
# ---------------------------------------------------------------------------

if HAS_HYPOTHESIS:

    @requires_hypothesis
    @settings(max_examples=25, deadline=None)
    @given(seed=st.integers(0, 2**32 - 1), cut=st.integers(60, 199))
    def test_i2_indicators_are_causal(seed: int, cut: int) -> None:
        """I2: for random OHLCV, an indicator value at bar t must not change
        when bars > t are perturbed (here: removed entirely)."""
        ind = pytest.importorskip("quantos.features.indicators")
        df = make_ohlcv(n=200, seed=seed)
        prefix = df.iloc[:cut]

        computations: list[tuple[str, pd.Series, pd.Series]] = [
            ("sma", ind.sma(df["close"], 14), ind.sma(prefix["close"], 14)),
            ("ema", ind.ema(df["close"], 14), ind.ema(prefix["close"], 14)),
            ("rsi", ind.rsi(df["close"], 14), ind.rsi(prefix["close"], 14)),
            (
                "atr",
                ind.atr(df["high"], df["low"], df["close"], 14),
                ind.atr(prefix["high"], prefix["low"], prefix["close"], 14),
            ),
            ("zscore", ind.zscore(df["close"], 20), ind.zscore(prefix["close"], 20)),
            ("returns", ind.returns(df["close"]), ind.returns(prefix["close"])),
            (
                "rolling_volatility",
                ind.rolling_volatility(df["close"], 20),
                ind.rolling_volatility(prefix["close"], 20),
            ),
        ]
        for name, full, truncated in computations:
            pd.testing.assert_series_equal(
                full.iloc[:cut], truncated, obj=f"{name} must be causal (I2)"
            )

    @requires_hypothesis
    @settings(max_examples=25, deadline=None)
    @given(seed=st.integers(0, 2**32 - 1))
    def test_i8_synthetic_data_is_reproducible(seed: int) -> None:
        """I8: the synthetic generator replays identically for a fixed seed."""
        collector = pytest.importorskip("quantos.data.collector")
        a = collector.synthetic_ohlcv("BTC/USDT", "1h", bars=64, seed=seed)
        b = collector.synthetic_ohlcv("BTC/USDT", "1h", bars=64, seed=seed)
        pd.testing.assert_frame_equal(a, b)

    @requires_hypothesis
    @settings(max_examples=10, deadline=None)
    @given(seed=st.integers(0, 2**32 - 1))
    def test_i8_committee_decision_replays(seed: int) -> None:
        """I8: a fixed snapshot deliberated twice yields the identical record."""
        collector = pytest.importorskip("quantos.data.collector")
        committee_mod = pytest.importorskip("quantos.committee.committee")
        snapshot = collector.DataCollector(force_synthetic=True).snapshot(
            "BTC/USDT", "1h", bars=120, seed=seed
        )
        committee = committee_mod.default_committee()
        assert_reproducible(lambda: committee.deliberate(snapshot).as_dict())
