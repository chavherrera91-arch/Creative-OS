"""WP-1.7 — backtest funnel: lagged positions (I2), baselines, WF, MC."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.backtest.engine import backtest, committee_signals
from quantos.backtest.monte_carlo import monte_carlo
from quantos.backtest.walk_forward import walk_forward
from quantos.features import indicators as ind


def flat(index: pd.Index) -> pd.Series:
    return pd.Series(0.0, index=index)


class TestBacktestEngine:
    def test_flat_positions_return_nothing(self, ohlcv: pd.DataFrame) -> None:
        result = backtest(ohlcv, flat(ohlcv.index))
        assert result.metrics["total_return"] == pytest.approx(0.0)
        assert (result.equity == 1.0).all()
        assert result.n_trades == 0

    def test_positions_are_lagged_no_look_ahead(self, ohlcv: pd.DataFrame) -> None:
        """I2: a position taken only at the last bar can never earn anything."""
        pos = flat(ohlcv.index)
        pos.iloc[-1] = 1.0
        result = backtest(ohlcv, pos)
        assert result.metrics["total_return"] == pytest.approx(0.0)
        assert (result.returns == 0.0).all()

    def test_late_position_cannot_affect_prior_bars(self, ohlcv: pd.DataFrame) -> None:
        k = 120
        late = flat(ohlcv.index)
        late.iloc[k:] = 1.0
        base = backtest(ohlcv, flat(ohlcv.index))
        with_late = backtest(ohlcv, late)
        # equity identical through bar k (position at k first affects bar k+1)
        pd.testing.assert_series_equal(base.equity.iloc[: k + 1], with_late.equity.iloc[: k + 1])

    def test_lag_beats_cheating(self) -> None:
        """Perfect knowledge of *today's* return earns nothing after the lag."""
        df = make_ohlcv(n=300, seed=9)
        oracle = np.sign(df["close"].pct_change().fillna(0.0))  # today's own return
        honest = backtest(df, oracle)
        # An un-lagged engine would compound |r| every bar; the honest one can't.
        cheat_total = float((1.0 + df["close"].pct_change().abs().fillna(0.0)).prod() - 1.0)
        assert honest.metrics["total_return"] < cheat_total * 0.5

    def test_costs_charged_on_turnover(self, ohlcv: pd.DataFrame) -> None:
        pos = pd.Series(1.0, index=ohlcv.index)
        with_costs = backtest(ohlcv, pos, fee_bps=10, slippage_bps=5)
        free = backtest(ohlcv, pos, fee_bps=0, slippage_bps=0)
        assert with_costs.metrics["total_return"] < free.metrics["total_return"]
        assert with_costs.n_trades == 1  # single entry, held throughout

    def test_metrics_finite_and_baselines_present(self, ohlcv: pd.DataFrame) -> None:
        pos = np.sign(ind.ema(ohlcv["close"], 10) - ind.ema(ohlcv["close"], 30)).fillna(0.0)
        result = backtest(ohlcv, pos)
        assert all(math.isfinite(v) for v in result.metrics.values())
        assert set(result.baselines) >= {
            "strategy",
            "buy_and_hold",
            "random",
            "beats_buy_and_hold",
            "beats_random",
        }
        json.dumps(result.as_dict())

    def test_deterministic(
        self, ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        pos = pd.Series(1.0, index=ohlcv.index)
        assert_reproducible(lambda: backtest(ohlcv, pos).as_dict())


class TestCommitteeSignals:
    def test_positions_valid_and_deterministic(self) -> None:
        df = make_ohlcv(n=140, seed=7, drift=0.003, vol=0.004)
        a = committee_signals(df, warmup=60, step=10)
        b = committee_signals(df, warmup=60, step=10)
        pd.testing.assert_series_equal(a, b)  # I8
        assert set(a.unique()) <= {-1.0, 0.0, 1.0}
        assert (a.iloc[:60] == 0.0).all()  # flat through warm-up

    def test_signals_are_causal(self) -> None:
        """I2: perturbing future bars must not change earlier positions."""
        df = make_ohlcv(n=140, seed=7, drift=0.003, vol=0.004)
        perturbed = df.copy()
        perturbed.iloc[120:, perturbed.columns.get_loc("close")] *= 0.5
        a = committee_signals(df, warmup=60, step=10).iloc[:120]
        b = committee_signals(perturbed, warmup=60, step=10).iloc[:120]
        pd.testing.assert_series_equal(a, b)


class TestWalkForward:
    @staticmethod
    def ema_cross(df: pd.DataFrame) -> pd.Series:
        return np.sign(ind.ema(df["close"], 10) - ind.ema(df["close"], 30)).fillna(0.0)

    def test_folds_partition_the_oos_window(self) -> None:
        df = make_ohlcv(n=420, seed=13)
        result = walk_forward(df, self.ema_cross, n_folds=4, min_train=100)
        assert len(result.folds) == 4
        assert sum(f.n_test_bars for f in result.folds) == 420 - 100
        assert len(result.oos_returns) == 320
        # folds are consecutive and non-overlapping
        for prev, cur in zip(result.folds, result.folds[1:], strict=False):
            assert prev.test_end < cur.test_start

    def test_oos_metrics_and_baselines(self) -> None:
        df = make_ohlcv(n=420, seed=13)
        result = walk_forward(df, self.ema_cross, n_folds=3, min_train=120)
        assert all(math.isfinite(v) for v in result.oos_metrics.values())
        assert "buy_and_hold" in result.baselines and "random" in result.baselines
        json.dumps(result.as_dict())

    def test_rejects_insufficient_history(self) -> None:
        df = make_ohlcv(n=90)
        with pytest.raises(ValueError, match="not enough bars"):
            walk_forward(df, self.ema_cross, n_folds=4, min_train=100)


class TestMonteCarlo:
    def test_percentiles_ordered_and_prob_loss_bounded(self, ohlcv: pd.DataFrame) -> None:
        returns = backtest(ohlcv, pd.Series(1.0, index=ohlcv.index)).returns
        result = monte_carlo(returns, n_sims=300, seed=42)
        p = result.total_return_percentiles
        assert p["p05"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]
        assert 0.0 <= result.prob_loss <= 1.0
        dd = result.max_drawdown_percentiles
        assert dd["p05"] <= dd["p50"] <= dd["p95"] <= 0.0
        json.dumps(result.as_dict())

    def test_deterministic_for_fixed_seed(
        self, ohlcv: pd.DataFrame, assert_reproducible: Callable[..., Any]
    ) -> None:
        returns = ohlcv["close"].pct_change().fillna(0.0)
        assert_reproducible(lambda: monte_carlo(returns, n_sims=100, seed=1).as_dict())
        a = monte_carlo(returns, n_sims=100, seed=1)
        b = monte_carlo(returns, n_sims=100, seed=2)
        assert a.as_dict() != b.as_dict()  # the seed genuinely drives the draw

    def test_rejects_empty_series(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            monte_carlo(pd.Series(dtype=float))
