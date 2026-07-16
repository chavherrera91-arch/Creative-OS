import numpy as np
import pandas as pd

from quantos.backtest.engine import backtest, committee_signals
from quantos.backtest.metrics import performance_metrics
from quantos.backtest.monte_carlo import monte_carlo
from quantos.backtest.walk_forward import walk_forward
from quantos.committee.committee import default_committee
from quantos.data.collector import synthetic_ohlcv


def test_long_only_matches_buy_and_hold_minus_costs():
    df = synthetic_ohlcv("BH", "1h", 300, seed=7, trend=0.003, volatility=0.006)
    positions = pd.Series(1.0, index=df.index)
    result = backtest(df, positions, fee=0.0)
    bh_return = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    # With zero fees and full long exposure, returns track buy & hold closely.
    assert abs(result.metrics.total_return - bh_return) < 0.02


def test_flat_positions_yield_zero_return():
    df = synthetic_ohlcv("F", "1h", 200, seed=8)
    positions = pd.Series(0.0, index=df.index)
    result = backtest(df, positions, fee=0.001)
    assert abs(result.metrics.total_return) < 1e-9


def test_no_lookahead_positions_are_lagged():
    df = synthetic_ohlcv("L", "1h", 50, seed=10)
    # Position only on the very last bar can't affect any prior return.
    positions = pd.Series(0.0, index=df.index)
    positions.iloc[-1] = 1.0
    result = backtest(df, positions, fee=0.0)
    assert abs(result.metrics.total_return) < 1e-9


def test_metrics_are_finite():
    df = synthetic_ohlcv("M", "1h", 300, seed=11, trend=0.002)
    r = df["close"].pct_change().dropna()
    m = performance_metrics(r)
    assert np.isfinite(m.sharpe)
    assert -1.0 <= m.max_drawdown <= 0.0
    assert 0.0 <= m.win_rate <= 1.0


def test_committee_backtest_runs():
    df = synthetic_ohlcv("CB", "1h", 400, seed=12, trend=0.002, volatility=0.008)
    positions = committee_signals(default_committee(), df, warmup=100, step=10)
    assert set(positions.unique()).issubset({-1.0, 0.0, 1.0})
    result = backtest(df, positions)
    assert result.equity.iloc[-1] > 0


def test_monte_carlo_distribution():
    df = synthetic_ohlcv("MC", "1h", 300, seed=13, trend=0.001)
    r = df["close"].pct_change().dropna()
    mc = monte_carlo(r, n_sims=200, seed=1)
    assert mc.n_sims == 200
    assert 0.0 <= mc.prob_loss <= 1.0
    assert mc.final_return["p05"] <= mc.final_return["p95"]


def test_walk_forward_folds():
    df = synthetic_ohlcv("WF", "1h", 600, seed=14, trend=0.002, volatility=0.008)
    committee = default_committee()

    def signal_fn(window, _params):
        return committee_signals(committee, window, warmup=20, step=10)

    result = walk_forward(df, signal_fn, n_folds=3)
    assert len(result.folds) >= 1
    assert result.combined_metrics is not None
