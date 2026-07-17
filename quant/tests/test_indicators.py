"""WP-1.2 — indicator correctness (hand-checked values) + causality (I2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.features import indicators as ind


class TestHandCheckedValues:
    def test_sma(self) -> None:
        out = ind.sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 2)
        expected = pd.Series([np.nan, 1.5, 2.5, 3.5, 4.5])
        pd.testing.assert_series_equal(out, expected)

    def test_ema_recursive(self) -> None:
        # period 3 -> alpha = 0.5; ema = [0, 5, 7.5]
        out = ind.ema(pd.Series([0.0, 10.0, 10.0]), 3)
        pd.testing.assert_series_equal(out, pd.Series([0.0, 5.0, 7.5]))

    def test_returns(self) -> None:
        out = ind.returns(pd.Series([100.0, 110.0, 99.0]))
        expected = pd.Series([np.nan, 0.10, -0.10])
        pd.testing.assert_series_equal(out, expected)

    def test_rsi_extremes_and_neutral(self) -> None:
        up = pd.Series(np.arange(1.0, 31.0))  # monotonic gains
        down = pd.Series(np.arange(30.0, 0.0, -1.0))  # monotonic losses
        flat = pd.Series(np.full(30, 7.0))
        assert ind.rsi(up, 14).iloc[-1] == pytest.approx(100.0)
        assert ind.rsi(down, 14).iloc[-1] == pytest.approx(0.0)
        assert ind.rsi(flat, 14).iloc[-1] == pytest.approx(50.0)
        assert ind.rsi(up, 14).iloc[:13].isna().all()  # warm-up is NaN, not fabricated

    def test_atr_constant_range(self) -> None:
        n = 30
        close = pd.Series(np.full(n, 100.0))
        high = close + 2.0
        low = close - 2.0
        # TR is constantly 4 -> ATR converges to exactly 4.
        out = ind.atr(high, low, close, 14)
        assert out.iloc[-1] == pytest.approx(4.0)

    def test_macd_zero_on_constant_series(self) -> None:
        out = ind.macd(pd.Series(np.full(60, 50.0)))
        assert (out["macd"].abs() < 1e-12).all()
        assert (out["histogram"].abs() < 1e-12).all()

    def test_bollinger_hand_checked(self) -> None:
        series = pd.Series([1.0, 2.0, 3.0])
        out = ind.bollinger(series, period=3, num_std=2.0)
        # mean 2, std 1 -> upper 4, lower 0, percent_b of 3.0 = 0.75
        assert out["middle"].iloc[-1] == pytest.approx(2.0)
        assert out["upper"].iloc[-1] == pytest.approx(4.0)
        assert out["lower"].iloc[-1] == pytest.approx(0.0)
        assert out["percent_b"].iloc[-1] == pytest.approx(0.75)

    def test_zscore_hand_checked(self) -> None:
        out = ind.zscore(pd.Series([1.0, 2.0, 3.0]), period=3)
        assert out.iloc[-1] == pytest.approx(1.0)  # (3 - 2) / 1

    def test_rolling_volatility_zero_when_flat(self) -> None:
        out = ind.rolling_volatility(pd.Series(np.full(40, 5.0)), period=10)
        assert out.iloc[-1] == pytest.approx(0.0)


class TestCausality:
    """No value at bar t may use data beyond t (I2)."""

    @pytest.mark.parametrize("cut", [60, 120, 199])
    def test_prefix_invariance(self, cut: int) -> None:
        df = make_ohlcv(n=200, seed=3)
        prefix = df.iloc[:cut]
        checks: dict[str, tuple[pd.Series, pd.Series]] = {
            "sma": (ind.sma(df["close"], 14), ind.sma(prefix["close"], 14)),
            "ema": (ind.ema(df["close"], 14), ind.ema(prefix["close"], 14)),
            "rsi": (ind.rsi(df["close"], 14), ind.rsi(prefix["close"], 14)),
            "atr": (
                ind.atr(df["high"], df["low"], df["close"], 14),
                ind.atr(prefix["high"], prefix["low"], prefix["close"], 14),
            ),
            "zscore": (ind.zscore(df["close"], 20), ind.zscore(prefix["close"], 20)),
            "returns": (ind.returns(df["close"]), ind.returns(prefix["close"])),
            "rolling_volatility": (
                ind.rolling_volatility(df["close"], 20),
                ind.rolling_volatility(prefix["close"], 20),
            ),
        }
        for name, (full, truncated) in checks.items():
            pd.testing.assert_series_equal(full.iloc[:cut], truncated, obj=f"{name} causality")
        for name, (full_df, trunc_df) in {
            "macd": (ind.macd(df["close"]), ind.macd(prefix["close"])),
            "bollinger": (ind.bollinger(df["close"]), ind.bollinger(prefix["close"])),
        }.items():
            pd.testing.assert_frame_equal(full_df.iloc[:cut], trunc_df, obj=f"{name} causality")

    def test_future_perturbation_does_not_leak(self) -> None:
        df = make_ohlcv(n=200, seed=5)
        perturbed = df.copy()
        perturbed.iloc[150:, perturbed.columns.get_loc("close")] *= 3.0  # violent future move
        a = ind.rsi(df["close"], 14).iloc[:150]
        b = ind.rsi(perturbed["close"], 14).iloc[:150]
        pd.testing.assert_series_equal(a, b)
