"""WP-5.3 — Strategy Lab: auto backtest, honest DSR/PBO ranking, cull, persist.

Acceptance: the ranking is deterministic offline (I8); culling keeps the
top-k; results (including the tested regime) are queryable from the store;
and — invariant I9 in action — a data-mined/lucky spec with a spectacular
in-sample Sharpe cannot top the ranking, because fitness is computed on the
held-out window and deflated by the Deflated Sharpe Ratio at the batch's
trial count, with the batch PBO recorded alongside.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.data.store.duckdb_store import DuckDBStore
from quantos.strategy.base import Rule, StrategySpec, compile_spec
from quantos.strategy.generator import generate
from quantos.strategy.lab import StrategyLab

# ---------------------------------------------------------------------------
# The I9 fixture: an alternation pattern that exists ONLY in-sample
# ---------------------------------------------------------------------------

N_BARS = 600
SPLIT = 360  # oos_fraction=0.4 puts the held-out window at bars [360, 600)


def overfit_trap_ohlcv() -> pd.DataFrame:
    """A deterministic price path with a data-mined trap.

    A steady exponential uptrend runs the whole sample (the *genuine* edge),
    while a ±1.5% bar-by-bar alternation exists **only in the in-sample
    window** — a one-bar mean-reversion rule harvests it spectacularly there
    and then bleeds once the pattern vanishes out of sample.
    """
    t = np.arange(N_BARS)
    base = 100.0 * np.exp(0.003 * t) * (1.0 + 0.002 * np.sin(t / 5.0))
    amp = np.where(t < SPLIT, 0.015, 0.015 * np.exp(-(t - SPLIT) / 8.0))
    close = base * (1.0 + amp * ((-1.0) ** t))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2024-01-01", periods=N_BARS, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * 1.002,
            "low": np.minimum(open_, close) * 0.998,
            "close": close,
            "volume": np.full(N_BARS, 100.0),
        },
        index=index,
    )


LUCKY = StrategySpec(
    name="lucky-meanrev",
    family="mean_reversion",
    indicators=("zscore",),
    rules=(Rule("zscore", "gt", 0.5, -1), Rule("zscore", "lt", -0.5, 1)),
    params={"zscore.period": 8},
    target_regimes=("RANGE",),
    rationale="one-bar reversal — the data-mined trap",
)
GENUINE = StrategySpec(
    name="genuine-trend",
    family="trend",
    indicators=("ema_ratio",),
    rules=(Rule("ema_ratio", "gt", 0.0, 1), Rule("ema_ratio", "lt", 0.0, -1)),
    params={"ema_ratio.period": 24},
    target_regimes=("TREND_UP",),
    rationale="ride the persistent drift — the genuine edge",
)


def test_lab_ranks_genuine_edge_above_data_mined_luck() -> None:
    ohlcv = overfit_trap_ohlcv()
    lab = StrategyLab(store=None, top_k=1, oos_fraction=0.4)
    result = lab.run([LUCKY, GENUINE], ohlcv)

    lucky, genuine = result.record_for(LUCKY), result.record_for(GENUINE)
    # the trap is real: naive in-sample ranking would crown the lucky spec
    assert lucky.is_metrics["sharpe"] > genuine.is_metrics["sharpe"]
    # ...but the lab's DSR-deflated OOS fitness cannot be fooled (I9)
    assert genuine.rank == 1 and lucky.rank == 2
    assert genuine.fitness > lucky.fitness
    assert genuine.validation["deflated_sharpe"] > 0.9
    assert lucky.validation["deflated_sharpe"] < 0.1
    # the cull keeps the genuine edge and drops the mined one
    assert result.survivors == [GENUINE]
    assert not lucky.survived
    # the batch carries its own honesty statistics (I9)
    assert math.isfinite(result.pbo) and 0.0 <= result.pbo <= 1.0
    assert result.n_trials == 2
    assert result.tested_regime == "TREND_UP"


def test_min_dsr_gate_culls_even_top_ranked_luck() -> None:
    # with only the lucky spec in the batch it ranks first by construction —
    # the DSR floor still refuses to let it survive (I9 gate)
    lab = StrategyLab(store=None, top_k=5, min_dsr=0.5, oos_fraction=0.4)
    result = lab.run([LUCKY], overfit_trap_ohlcv())
    assert result.records[0].rank == 1
    assert result.survivors == []


# ---------------------------------------------------------------------------
# Determinism (I8), culling, persistence
# ---------------------------------------------------------------------------


def test_ranking_is_deterministic_offline(assert_reproducible) -> None:
    ohlcv = make_ohlcv(n=400, seed=11)
    specs = generate(6, seed=21)
    assert_reproducible(lambda: StrategyLab(store=None, top_k=3).run(specs, ohlcv).as_dict())


def test_culling_keeps_the_top_k() -> None:
    ohlcv = make_ohlcv(n=400, seed=11)
    specs = generate(8, seed=4)
    result = StrategyLab(store=None, top_k=3, min_dsr=-1.0).run(specs, ohlcv)
    assert [r.rank for r in result.records] == list(range(1, 9))
    fitness = [r.fitness for r in result.records]
    assert fitness == sorted(fitness, reverse=True)
    assert len(result.survivors) == 3
    assert result.survivors == [r.spec for r in result.records[:3]]


def test_results_with_tested_regime_queryable_from_store() -> None:
    store = DuckDBStore()
    ohlcv = make_ohlcv(n=400, seed=11)
    specs = generate(5, seed=8)
    lab = StrategyLab(store=store, top_k=2, symbol="BTC/USDT")
    result = lab.run(specs, ohlcv)

    rows = store.read("features", "strategy_lab")
    assert len(rows) == 5
    assert {"run_id", "spec_hash", "family", "tested_regime", "fitness", "survived",
            "deflated_sharpe", "pbo", "target_regimes", "spec_json"} <= set(rows.columns)
    assert (rows["run_id"] == result.run_id).all()
    assert set(rows["tested_regime"]) == {result.tested_regime}
    assert int(rows["survived"].sum()) == 2
    # the stored spec replays to the exact strategy that was tested (I8)
    top_row = rows.loc[rows["rank"] == 1].iloc[0]
    import json

    restored = StrategySpec.from_dict(json.loads(top_row["spec_json"]))
    assert restored.spec_hash() == top_row["spec_hash"]

    # re-running the same batch is idempotent (deterministic run_id + upsert)
    lab.run(specs, ohlcv)
    assert len(store.read("features", "strategy_lab")) == 5


def test_lab_accepts_ready_strategy_objects() -> None:
    ohlcv = make_ohlcv(n=300, seed=2)
    strategy = compile_spec(GENUINE)  # a Strategy, not a bare spec (I7)
    result = StrategyLab(store=None).run([strategy, LUCKY], ohlcv)
    assert {r.spec.name for r in result.records} == {"genuine-trend", "lucky-meanrev"}
    with pytest.raises(TypeError):
        StrategyLab(store=None).run([object()], ohlcv)  # type: ignore[list-item]


def test_lab_rejects_bad_inputs() -> None:
    ohlcv = make_ohlcv(n=100)
    with pytest.raises(ValueError):
        StrategyLab(store=None).run([], ohlcv)
    with pytest.raises(ValueError):
        StrategyLab(oos_fraction=0.0)
    with pytest.raises(ValueError):
        StrategyLab(top_k=0)
    with pytest.raises(ValueError):
        StrategyLab(store=None).run([GENUINE], ohlcv.iloc[:3])


def test_single_candidate_has_nan_pbo_and_mlflow_stays_optional(tmp_path) -> None:
    # mlflow is not installed in this environment: the lazy path must no-op
    lab = StrategyLab(store=None, mlflow_uri=f"file://{tmp_path}")
    result = lab.run([GENUINE], make_ohlcv(n=300, seed=2))
    assert math.isnan(result.pbo)  # PBO needs at least two trials
    assert result.records[0].rank == 1
