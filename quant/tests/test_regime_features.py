"""WP-4.2 — regime features: causal (I2), deterministic (I8), discriminative."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.data.models import MarketSnapshot
from quantos.features.regime_features import (
    adx,
    efficiency_ratio,
    ema_slope,
    event_proximity,
    hurst_exponent,
    regime_feature_frame,
    snapshot_regime_features,
)


def make_choppy(n: int = 200, period: int = 10, amp: float = 0.02, seed: int = 11) -> pd.DataFrame:
    """A directionless oscillation: price ping-pongs around a flat level."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100.0 * (1.0 + amp * np.sin(2.0 * np.pi * t / period))
    close += rng.normal(0.0, 0.05, size=n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    spread = np.abs(rng.normal(0.0, 0.1, size=n))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.uniform(50.0, 150.0, size=n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
    )
    return frame


class TestTrendStrength:
    def test_adx_high_on_trend_low_on_chop(self, uptrend_ohlcv: pd.DataFrame) -> None:
        choppy = make_choppy()
        adx_trend = float(
            adx(uptrend_ohlcv["high"], uptrend_ohlcv["low"], uptrend_ohlcv["close"]).iloc[-1]
        )
        adx_chop = float(adx(choppy["high"], choppy["low"], choppy["close"]).iloc[-1])
        assert adx_trend > 25.0
        assert adx_trend > adx_chop

    def test_ema_slope_signed(
        self, uptrend_ohlcv: pd.DataFrame, downtrend_ohlcv: pd.DataFrame
    ) -> None:
        assert float(ema_slope(uptrend_ohlcv["close"]).iloc[-1]) > 0.0
        assert float(ema_slope(downtrend_ohlcv["close"]).iloc[-1]) < 0.0

    def test_efficiency_ratio_trend_vs_chop(self, uptrend_ohlcv: pd.DataFrame) -> None:
        er_trend = float(efficiency_ratio(uptrend_ohlcv["close"]).iloc[-1])
        er_chop = float(efficiency_ratio(make_choppy()["close"]).iloc[-1])
        assert 0.0 <= er_chop <= 1.0
        assert er_trend > 0.4
        assert er_trend > er_chop

    def test_hurst_trend_vs_mean_reversion(self, uptrend_ohlcv: pd.DataFrame) -> None:
        assert hurst_exponent(uptrend_ohlcv["close"]) > 0.5
        assert hurst_exponent(make_choppy()["close"]) < 0.5

    def test_trend_fixture_scores_high_choppy_scores_low(
        self, uptrend_ohlcv: pd.DataFrame
    ) -> None:
        """The WP acceptance in one place, over the snapshot feature dict."""
        trend = snapshot_regime_features(MarketSnapshot("BTC/USDT", "1h", uptrend_ohlcv))
        chop = snapshot_regime_features(MarketSnapshot("BTC/USDT", "1h", make_choppy()))
        assert abs(trend["trend_intensity"]) > abs(chop["trend_intensity"])
        assert trend["adx"] > chop["adx"]
        assert trend["efficiency_ratio"] > chop["efficiency_ratio"]


class TestVolatilityAndVolume:
    def test_vol_ratio_reads_a_late_vol_burst(self) -> None:
        calm = make_ohlcv(n=150, vol=0.003, seed=3)
        wild = make_ohlcv(n=50, vol=0.03, seed=4, start="2024-01-07 06:00")
        frame = regime_feature_frame(pd.concat([calm, wild]))
        assert float(frame["vol_ratio"].iloc[-1]) > 2.0
        assert float(frame["realised_vol"].iloc[-1]) > float(frame["realised_vol"].iloc[140])
        assert float(frame["atr_pct"].iloc[-1]) > float(frame["atr_pct"].iloc[140])

    def test_volume_ratio_reads_a_volume_regime_shift(self, ohlcv: pd.DataFrame) -> None:
        boosted = ohlcv.copy()
        boosted.iloc[-30:, boosted.columns.get_loc("volume")] *= 5.0
        frame = regime_feature_frame(boosted)
        assert float(frame["volume_ratio"].iloc[-1]) > 2.0

    def test_drawdown_is_causal_running_peak(self) -> None:
        crash = pd.concat(
            [
                make_ohlcv(n=100, drift=0.002, vol=0.004, seed=5),
                make_ohlcv(n=50, drift=-0.02, vol=0.02, seed=6, start="2024-01-05 04:00"),
            ]
        )
        frame = regime_feature_frame(crash)
        assert float(frame["drawdown"].iloc[-1]) < -0.3
        assert (frame["drawdown"].dropna() <= 1e-12).all()


class TestEventProximity:
    def test_no_events_scores_zero(self) -> None:
        assert event_proximity([]) == 0.0
        assert event_proximity(None) == 0.0

    def test_imminent_high_impact_event_scores_one(self) -> None:
        events = [{"name": "FOMC", "impact": "high"}]
        assert event_proximity(events) == 1.0

    def test_distance_decays_the_score(self) -> None:
        as_of = pd.Timestamp("2024-01-10 12:00", tz="UTC")
        near = [{"name": "CPI", "impact": "high", "time": "2024-01-10 14:00+00:00"}]
        far = [{"name": "CPI", "impact": "high", "time": "2024-01-12 06:00+00:00"}]
        gone = [{"name": "CPI", "impact": "high", "time": "2024-02-01 00:00+00:00"}]
        assert event_proximity(near, as_of) > event_proximity(far, as_of) > 0.0
        assert event_proximity(gone, as_of) == 0.0

    def test_medium_impact_weighs_less_than_high(self) -> None:
        high = [{"name": "NFP", "impact": "high"}]
        medium = [{"name": "PMI", "impact": "medium"}]
        assert event_proximity(high) > event_proximity(medium) > 0.0


class TestCausalityAndDeterminism:
    """I2 prefix invariance and I8 reproducibility over the whole frame."""

    @pytest.mark.parametrize("cut", [80, 140, 190])
    def test_prefix_invariance(self, ohlcv: pd.DataFrame, cut: int) -> None:
        full = regime_feature_frame(ohlcv)
        prefix = regime_feature_frame(ohlcv.iloc[:cut])
        pd.testing.assert_frame_equal(full.iloc[:cut], prefix)

    def test_future_perturbation_cannot_change_the_past(self, ohlcv: pd.DataFrame) -> None:
        perturbed = ohlcv.copy()
        perturbed.iloc[150:, perturbed.columns.get_loc("close")] *= 1.5
        pd.testing.assert_frame_equal(
            regime_feature_frame(ohlcv).iloc[:150],
            regime_feature_frame(perturbed).iloc[:150],
        )

    def test_snapshot_features_reproducible_and_finite(
        self, ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        snapshot = MarketSnapshot("BTC/USDT", "1h", ohlcv)
        features = assert_reproducible(snapshot_regime_features, snapshot)
        assert all(np.isfinite(v) for v in features.values())
        assert {"adx", "vol_ratio", "hurst", "event_proximity", "drawdown"} <= set(features)

    def test_short_history_yields_neutral_defaults(self) -> None:
        features = snapshot_regime_features(MarketSnapshot("BTC/USDT", "1h", make_ohlcv(n=10)))
        assert features["vol_ratio"] == 1.0
        assert features["adx"] == 0.0
        assert features["hurst"] == 0.5
