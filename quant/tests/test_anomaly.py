"""WP-4.1 — anomaly detection: injected spikes flagged, calm regions clean (I2/I8)."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.anomaly.base import ANOMALY_KINDS, AnomalyDetector, anomaly_summary
from quantos.anomaly.detectors import IsolationForestDetector, ZScoreDetector

HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None

SPIKE_AT = 150


def with_volume_spike(ohlcv: pd.DataFrame, at: int = SPIKE_AT, mult: float = 25.0) -> pd.DataFrame:
    out = ohlcv.copy()
    out.iloc[at, out.columns.get_loc("volume")] *= mult
    return out


def with_price_jump(ohlcv: pd.DataFrame, at: int = SPIKE_AT, jump: float = 0.12) -> pd.DataFrame:
    """Multiply every bar from ``at`` onward: a one-bar return burst at ``at``."""
    out = ohlcv.copy()
    for column in ("open", "high", "low", "close"):
        out.iloc[at:, out.columns.get_loc(column)] *= 1.0 + jump
    out.iloc[at, out.columns.get_loc("open")] /= 1.0 + jump  # the jump happens intra-bar
    return out


def with_gap(ohlcv: pd.DataFrame, at: int = SPIKE_AT, gap: float = 0.10) -> pd.DataFrame:
    out = ohlcv.copy()
    out.iloc[at, out.columns.get_loc("open")] *= 1.0 + gap
    out.iloc[at, out.columns.get_loc("high")] = max(
        out["high"].iloc[at], out["open"].iloc[at]
    )
    return out


def with_wash_trading(ohlcv: pd.DataFrame, at: int = SPIKE_AT, mult: float = 25.0) -> pd.DataFrame:
    """Huge volume printed on a bar that barely moves — fake-liquidity signature."""
    out = ohlcv.copy()
    close = out["close"].iloc[at - 1]
    out.iloc[at, out.columns.get_loc("open")] = close
    out.iloc[at, out.columns.get_loc("close")] = close * 1.0001
    out.iloc[at, out.columns.get_loc("high")] = close * 1.0002
    out.iloc[at, out.columns.get_loc("low")] = close * 0.9999
    out.iloc[at, out.columns.get_loc("volume")] *= mult
    return out


class TestZScoreDetectorFlags:
    """Acceptance: the injected spike is flagged, the calm region is not."""

    def test_satisfies_the_port(self) -> None:
        assert isinstance(ZScoreDetector(), AnomalyDetector)
        assert ZScoreDetector().fit(make_ohlcv()) is not None

    def test_volume_spike_flagged_calm_region_clean(self, ohlcv: pd.DataFrame) -> None:
        detector = ZScoreDetector()
        flags = detector.flags(with_volume_spike(ohlcv))
        assert bool(flags.iloc[SPIKE_AT])
        calm = flags.drop(flags.index[SPIKE_AT])
        assert not calm.any(), f"false flags at {list(calm[calm].index)}"

    def test_clean_series_has_no_flags(self, ohlcv: pd.DataFrame) -> None:
        assert not ZScoreDetector().flags(ohlcv).any()

    @pytest.mark.parametrize(
        ("inject", "kind"),
        [
            (with_volume_spike, "volume_spike"),
            (with_price_jump, "volatility_burst"),
            (with_gap, "gap"),
            (with_wash_trading, "wash_trading"),
        ],
        ids=["volume", "vol_burst", "gap", "wash"],
    )
    def test_each_kind_is_attributed(
        self, ohlcv: pd.DataFrame, inject: Callable[[pd.DataFrame], pd.DataFrame], kind: str
    ) -> None:
        detector = ZScoreDetector()
        kinds = detector.kind_scores(inject(ohlcv))
        assert list(kinds.columns) == list(ANOMALY_KINDS)
        assert kinds[kind].iloc[SPIKE_AT] >= detector.threshold
        assert bool(detector.flags(inject(ohlcv)).iloc[SPIKE_AT])

    def test_score_is_higher_at_the_spike_than_anywhere_calm(self, ohlcv: pd.DataFrame) -> None:
        score = ZScoreDetector().score(with_volume_spike(ohlcv))
        assert score.iloc[SPIKE_AT] == score.max()
        assert score.iloc[SPIKE_AT] > 2 * score.drop(score.index[SPIKE_AT]).max()


class TestCausality:
    """I2: the score at bar t is a function of bars <= t only."""

    @pytest.mark.parametrize("cut", [80, SPIKE_AT + 1, 190])
    def test_prefix_invariance(self, ohlcv: pd.DataFrame, cut: int) -> None:
        detector = ZScoreDetector()
        full = detector.score(with_volume_spike(ohlcv))
        prefix = detector.score(with_volume_spike(ohlcv).iloc[:cut])
        pd.testing.assert_series_equal(full.iloc[:cut], prefix)

    def test_future_perturbation_cannot_change_the_past(self, ohlcv: pd.DataFrame) -> None:
        detector = ZScoreDetector()
        base = detector.score(ohlcv)
        perturbed = detector.score(with_volume_spike(ohlcv, at=180, mult=100.0))
        pd.testing.assert_series_equal(base.iloc[:180], perturbed.iloc[:180])

    def test_spike_does_not_join_its_own_baseline(self, ohlcv: pd.DataFrame) -> None:
        """The shifted baseline means the spike bar itself scores at full force."""
        spiked = with_volume_spike(ohlcv)
        score = ZScoreDetector().kind_scores(spiked)["volume_spike"]
        assert score.iloc[SPIKE_AT] > 5.0


class TestDeterminismAndSummary:
    def test_score_is_reproducible(
        self, ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        assert_reproducible(ZScoreDetector().score, with_volume_spike(ohlcv))

    def test_summary_reports_the_active_anomaly(self, ohlcv: pd.DataFrame) -> None:
        spiked = with_volume_spike(ohlcv, at=len(ohlcv) - 1)
        summary = anomaly_summary(ZScoreDetector(), spiked)
        assert summary["active"] is True
        assert summary["kinds"]["volume_spike"]["flag"] is True
        assert summary["score"] >= summary["threshold"]
        json.dumps(summary)

    def test_summary_is_quiet_on_calm_data(self, ohlcv: pd.DataFrame) -> None:
        summary = anomaly_summary(ZScoreDetector(), ohlcv)
        assert summary["active"] is False
        assert set(summary["kinds"]) == set(ANOMALY_KINDS)


class TestIsolationForestIsOptional:
    """The [ml] detector is lazy: importable always, usable only with sklearn."""

    def test_constructing_needs_no_sklearn(self) -> None:
        detector = IsolationForestDetector(seed=42)
        assert isinstance(detector, AnomalyDetector)

    @pytest.mark.skipif(HAS_SKLEARN, reason="sklearn installed — lazy failure not reachable")
    def test_fit_without_sklearn_raises_helpfully(self, ohlcv: pd.DataFrame) -> None:
        with pytest.raises(ImportError, match="ml"):
            IsolationForestDetector().fit(ohlcv)

    @pytest.mark.skipif(not HAS_SKLEARN, reason="sklearn not installed")
    def test_flags_the_spike_when_available(self, ohlcv: pd.DataFrame) -> None:  # pragma: no cover
        detector = IsolationForestDetector(seed=42).fit(ohlcv)
        assert bool(detector.flags(with_volume_spike(ohlcv)).iloc[SPIKE_AT])
