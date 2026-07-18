"""WP-3.3 — anti-overfitting statistics: DSR, PBO, purged+embargoed CPCV (I9)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.backtest.validation import (
    CombinatorialPurgedCV,
    deflated_sharpe,
    deflated_sharpe_from_returns,
    expected_max_sharpe,
    norm_cdf,
    norm_ppf,
    pbo,
    probabilistic_sharpe,
)


class TestNormalDistribution:
    def test_cdf_known_values(self) -> None:
        assert norm_cdf(0.0) == pytest.approx(0.5)
        assert norm_cdf(1.959963985) == pytest.approx(0.975, abs=1e-6)
        assert norm_cdf(-1.959963985) == pytest.approx(0.025, abs=1e-6)

    def test_ppf_known_values(self) -> None:
        assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-9)
        assert norm_ppf(0.975) == pytest.approx(1.959963985, abs=1e-6)
        assert norm_ppf(0.001) == pytest.approx(-3.090232306, abs=1e-6)

    def test_ppf_inverts_cdf(self) -> None:
        for x in (-3.0, -1.2, -0.1, 0.0, 0.7, 2.5):
            assert norm_ppf(norm_cdf(x)) == pytest.approx(x, abs=1e-7)

    def test_ppf_rejects_out_of_domain(self) -> None:
        with pytest.raises(ValueError):
            norm_ppf(0.0)
        with pytest.raises(ValueError):
            norm_ppf(1.0)


class TestDeflatedSharpe:
    def test_shrinks_toward_zero_as_trials_grow(self) -> None:
        """Acceptance: a fixed Sharpe means less the more trials produced it."""
        fixed = dict(sharpe=0.1, skew=0.0, kurtosis=3.0, n_obs=500)
        dsrs = [deflated_sharpe(n_trials=n, **fixed) for n in (1, 10, 100, 1000, 10_000)]
        assert all(a > b for a, b in zip(dsrs, dsrs[1:], strict=False))  # strictly shrinking
        assert dsrs[0] > 0.95  # a genuine single-trial SR 0.1 over 500 bars
        assert dsrs[-1] < 0.06  # the same SR as the best of 10k trials: noise

    def test_single_trial_equals_psr_vs_zero(self) -> None:
        assert deflated_sharpe(0.08, 1, n_obs=400) == pytest.approx(
            probabilistic_sharpe(0.08, 0.0, 400)
        )

    def test_expected_max_sharpe_grows_with_trials(self) -> None:
        v = 1.0 / 499
        e10 = expected_max_sharpe(10, v)
        e100 = expected_max_sharpe(100, v)
        assert expected_max_sharpe(1, v) == 0.0
        assert 0.0 < e10 < e100

    def test_fat_tails_reduce_confidence(self) -> None:
        thin = deflated_sharpe(0.1, 10, skew=0.0, kurtosis=3.0, n_obs=500)
        fat = deflated_sharpe(0.1, 10, skew=-1.0, kurtosis=10.0, n_obs=500)
        assert fat < thin

    def test_from_returns_report(self) -> None:
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.01, size=600))
        report = deflated_sharpe_from_returns(returns, n_trials=5)
        assert set(report) == {
            "sharpe", "skew", "kurtosis", "n_obs", "n_trials",
            "expected_max_sharpe", "deflated_sharpe",
        }
        assert report["n_obs"] == 600.0
        assert 0.0 <= report["deflated_sharpe"] <= 1.0

    def test_degenerate_inputs_are_safe(self) -> None:
        assert deflated_sharpe(0.5, 10, n_obs=1) == 0.0
        empty = deflated_sharpe_from_returns(pd.Series(dtype=float))
        assert empty["deflated_sharpe"] == 0.0


class TestPBO:
    @staticmethod
    def panels(genuine: bool, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
        """Seeded IS/OOS panels: 20 noise trials, optionally one real edge."""
        rng = np.random.default_rng(seed)
        is_m = rng.normal(0.0, 0.01, size=(240, 20))
        oos_m = rng.normal(0.0, 0.01, size=(240, 20))
        if genuine:
            is_m[:, 0] += 0.005  # a real, persistent edge in trial 0
            oos_m[:, 0] += 0.005
        return is_m, oos_m

    def test_high_for_overfit_selection(self) -> None:
        """Pure noise: the IS winner is luck, so it beats the OOS median only by chance."""
        is_m, oos_m = self.panels(genuine=False)
        assert pbo(is_m, oos_m) > 0.35

    def test_low_for_genuine_edge(self) -> None:
        is_m, oos_m = self.panels(genuine=True)
        assert pbo(is_m, oos_m) < 0.10

    def test_overfit_exceeds_genuine(self) -> None:
        noise = pbo(*self.panels(genuine=False))
        real = pbo(*self.panels(genuine=True))
        assert noise > real

    def test_accepts_dataframes(self) -> None:
        is_m, oos_m = self.panels(genuine=True)
        assert pbo(pd.DataFrame(is_m), pd.DataFrame(oos_m)) == pbo(is_m, oos_m)

    def test_deterministic(self, assert_reproducible: Callable[..., Any]) -> None:
        is_m, oos_m = self.panels(genuine=False)
        assert_reproducible(lambda: pbo(is_m, oos_m))

    def test_input_validation(self) -> None:
        good = np.zeros((100, 3))
        with pytest.raises(ValueError):
            pbo(good, np.zeros((100, 4)))  # trial-count mismatch
        with pytest.raises(ValueError):
            pbo(good, good, n_blocks=7)  # odd blocks
        with pytest.raises(ValueError):
            pbo(np.zeros((100, 1)), np.zeros((100, 1)))  # nothing to rank against


class TestCombinatorialPurgedCV:
    def test_fold_count_and_coverage(self) -> None:
        cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)
        X = np.arange(120)
        folds = list(cv.split(X))
        assert len(folds) == cv.n_folds == 15
        for train, test in folds:
            assert len(test) == 40  # 2 groups of 20
            assert len(np.intersect1d(train, test)) == 0

    def test_no_overlapping_label_windows(self) -> None:
        """Acceptance: with h-bar labels, no train label window touches a test window."""
        n, horizon = 120, 5
        cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)
        label_end = np.minimum(np.arange(n) + horizon - 1, n - 1)
        for train, test in cv.split(np.arange(n), label_times=label_end):
            for t in test:
                # train sample u's label window is [u, label_end[u]];
                # test sample t's is [t, label_end[t]] — they must not intersect.
                overlap = (label_end[train] >= t) & (train <= label_end[t])
                assert not overlap.any()

    def test_embargo_removes_post_test_bars(self) -> None:
        cv = CombinatorialPurgedCV(n_groups=4, n_test_groups=1, embargo=5)
        X = np.arange(80)
        for train, test in cv.split(X):
            tail = int(test.max())
            embargoed = np.arange(tail + 1, min(tail + 6, 80))
            assert len(np.intersect1d(train, embargoed)) == 0

    def test_split_embargo_override(self) -> None:
        cv = CombinatorialPurgedCV(n_groups=4, n_test_groups=1, embargo=0)
        X = np.arange(80)
        with_embargo = [len(tr) for tr, _ in cv.split(X, embargo=10)]
        without = [len(tr) for tr, _ in cv.split(X)]
        assert sum(with_embargo) < sum(without)

    def test_deterministic(self, assert_reproducible: Callable[..., Any]) -> None:
        cv = CombinatorialPurgedCV(n_groups=5, n_test_groups=2, embargo=3)
        X = np.arange(100)
        assert_reproducible(lambda: [(t.tolist(), s.tolist()) for t, s in cv.split(X)])

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError):
            CombinatorialPurgedCV(n_groups=3, n_test_groups=3)
        with pytest.raises(ValueError):
            CombinatorialPurgedCV(embargo=-1)
        with pytest.raises(ValueError):
            list(CombinatorialPurgedCV(n_groups=10).split(np.arange(5)))


class TestWalkForwardCarriesValidation:
    def test_oos_result_reports_dsr(self) -> None:
        """I9: the walk-forward OOS path always carries its Deflated Sharpe."""
        from quantos.backtest.walk_forward import walk_forward
        from quantos.features.indicators import sma

        def signal_fn(df: pd.DataFrame) -> pd.Series:
            fast, slow = sma(df["close"], 10), sma(df["close"], 30)
            return (fast > slow).astype(float)

        ohlcv = make_ohlcv(n=400, drift=0.001, vol=0.008, seed=42)
        result = walk_forward(ohlcv, signal_fn, n_folds=4, min_train=100, n_trials=12)
        assert result.validation["n_trials"] == 12.0
        assert 0.0 <= result.validation["deflated_sharpe"] <= 1.0
        assert "validation" in result.as_dict()

    def test_more_trials_never_raise_the_dsr(self) -> None:
        from quantos.backtest.walk_forward import walk_forward
        from quantos.features.indicators import sma

        def signal_fn(df: pd.DataFrame) -> pd.Series:
            return (df["close"] > sma(df["close"], 20)).astype(float)

        ohlcv = make_ohlcv(n=400, drift=0.001, vol=0.008, seed=42)
        one = walk_forward(ohlcv, signal_fn, n_folds=4, min_train=100, n_trials=1)
        many = walk_forward(ohlcv, signal_fn, n_folds=4, min_train=100, n_trials=500)
        assert many.validation["deflated_sharpe"] <= one.validation["deflated_sharpe"]
