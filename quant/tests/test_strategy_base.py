"""WP-5.1 — Strategy base, spec hashing/versioning and the block registry.

Acceptance: a spec round-trips to signals; signals never use future bars
(I2, prefix-invariance and future-perturbation checks over every registered
block); the same spec always yields the same signals (I8); the spec is
hashable, versioned and serialisable; the registry accepts new blocks
without core edits (I7); the M4 simulator consumes the same canonical port.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.scenarios.simulator import SignalStrategy as SimulatorSignalStrategy
from quantos.strategy.base import (
    Comparator,
    IndicatorBlock,
    IndicatorStrategy,
    ParamSpec,
    Rule,
    SignalStrategy,
    Strategy,
    StrategyRegistry,
    StrategySpec,
    compile_spec,
    registry,
)


def trend_spec(period: float = 20.0) -> StrategySpec:
    """A tiny trend-following spec used across the tests."""
    return StrategySpec(
        name="ema-trend",
        version="1",
        family="trend",
        indicators=("ema_ratio",),
        rules=(
            Rule("ema_ratio", "gt", 0.0, action=1),
            Rule("ema_ratio", "lt", 0.0, action=-1),
        ),
        params={"ema_ratio.period": period},
        target_regimes=("TREND_UP", "TREND_DOWN"),
        rationale="ride the side of the EMA the price is on",
    )


# ---------------------------------------------------------------------------
# Spec: validation, hashing, versioning, serialisation (I8)
# ---------------------------------------------------------------------------


def test_spec_roundtrips_and_hashes_stably() -> None:
    spec = trend_spec()
    clone = StrategySpec.from_dict(spec.as_dict())
    assert clone == spec
    assert clone.spec_hash() == spec.spec_hash()
    assert hash(clone) == hash(spec)
    assert spec.key.startswith("ema-trend@1#")
    # usable in sets/dicts (hashable)
    assert len({spec, clone}) == 1


def test_spec_hash_changes_with_params_and_version() -> None:
    spec = trend_spec()
    assert spec.spec_hash() != trend_spec(period=30.0).spec_hash()
    bumped = StrategySpec.from_dict({**spec.as_dict(), "version": "2"})
    assert bumped.spec_hash() != spec.spec_hash()
    assert bumped != spec


def test_spec_validation_rejects_bad_specs() -> None:
    with pytest.raises(ValueError):
        StrategySpec(name="x", indicators=(), rules=(Rule("ema_ratio", "gt", 0.0, 1),))
    with pytest.raises(ValueError):  # rule references unlisted indicator
        StrategySpec(name="x", indicators=("rsi",), rules=(Rule("zscore", "gt", 0.0, 1),))
    with pytest.raises(ValueError):  # duplicate indicator set entries
        StrategySpec(
            name="x", indicators=("rsi", "rsi"), rules=(Rule("rsi", "gt", 0.0, 1),)
        )
    with pytest.raises(ValueError):  # unknown regime label
        StrategySpec(
            name="x",
            indicators=("rsi",),
            rules=(Rule("rsi", "gt", 0.0, 1),),
            target_regimes=("SIDEWAYS",),
        )
    with pytest.raises(ValueError):  # illegal action
        Rule("rsi", "gt", 0.0, action=2)


def test_compile_rejects_unregistered_blocks() -> None:
    spec = StrategySpec(name="x", indicators=("rsi",), rules=(Rule("rsi", "wat", 0.0, 1),))
    with pytest.raises(KeyError):
        compile_spec(spec)
    ghost = StrategySpec(name="x", indicators=("no_such",), rules=(Rule("no_such", "gt", 0.0, 1),))
    with pytest.raises(KeyError):
        compile_spec(ghost)


# ---------------------------------------------------------------------------
# Signals: shape, determinism (I8) and the canonical port (I7)
# ---------------------------------------------------------------------------


def test_spec_roundtrips_to_signals(uptrend_ohlcv: pd.DataFrame) -> None:
    strategy = compile_spec(trend_spec())
    signals = strategy.signals(uptrend_ohlcv)
    assert isinstance(signals, pd.Series)
    assert signals.index.equals(uptrend_ohlcv.index)
    assert signals.between(-1.0, 1.0).all()
    assert not signals.isna().any()
    # an uptrend fixture should end up net long (each rule carries half the
    # conviction weight, so the one-sided "gt" vote reads +0.5)
    assert signals.iloc[-50:].mean() > 0.4


def test_same_spec_same_signals(ohlcv: pd.DataFrame, assert_reproducible) -> None:
    spec = trend_spec()
    assert_reproducible(lambda: compile_spec(spec).signals(ohlcv))
    # two independently compiled copies of an equal spec agree bit-for-bit
    a = IndicatorStrategy(spec).signals(ohlcv)
    b = IndicatorStrategy(StrategySpec.from_dict(spec.as_dict())).signals(ohlcv)
    pd.testing.assert_series_equal(a, b)


def test_indicator_strategy_satisfies_the_canonical_port() -> None:
    strategy = compile_spec(trend_spec())
    assert isinstance(strategy, Strategy)
    assert isinstance(strategy, SignalStrategy)
    # one canonical port, not two: the M4 simulator shares the same Protocol
    assert SimulatorSignalStrategy is SignalStrategy
    assert isinstance(strategy, SimulatorSignalStrategy)


# ---------------------------------------------------------------------------
# No look-ahead (I2): prefix invariance + future perturbation, every block
# ---------------------------------------------------------------------------


def _one_block_spec(name: str) -> StrategySpec:
    block = registry.indicator(name)
    threshold = block.threshold.default
    return StrategySpec(
        name=f"probe-{name}",
        indicators=(name,),
        rules=(
            Rule(name, "gt", threshold, action=1),
            Rule(name, "cross_below", threshold, action=-1),
        ),
    )


@pytest.mark.parametrize("name", registry.indicator_names())
def test_signals_are_prefix_invariant_for_every_block(name: str) -> None:
    ohlcv = make_ohlcv(n=160, seed=3)
    strategy = compile_spec(_one_block_spec(name))
    full = strategy.signals(ohlcv)
    for cut in (40, 90, 159):
        prefix = strategy.signals(ohlcv.iloc[:cut])
        pd.testing.assert_series_equal(prefix, full.iloc[:cut])


def test_signals_ignore_future_perturbations() -> None:
    ohlcv = make_ohlcv(n=160, seed=3)
    spec = StrategySpec(
        name="multi",
        indicators=("ema_ratio", "zscore", "channel_pos"),
        rules=(
            Rule("ema_ratio", "gt", 0.0, action=1),
            Rule("zscore", "lt", -1.0, action=1),
            Rule("channel_pos", "cross_above", 0.3, action=-1),
        ),
    )
    strategy = compile_spec(spec)
    base = strategy.signals(ohlcv)
    t = 100
    tampered = ohlcv.copy()
    tampered.iloc[t + 1 :, :] = tampered.iloc[t + 1 :, :] * 7.5  # rewrite the future
    perturbed = strategy.signals(tampered)
    pd.testing.assert_series_equal(perturbed.iloc[: t + 1], base.iloc[: t + 1])


# ---------------------------------------------------------------------------
# Registry: new blocks plug in without core edits (I7)
# ---------------------------------------------------------------------------


def test_registry_accepts_new_blocks_without_core_edits(ohlcv: pd.DataFrame) -> None:
    reg = StrategyRegistry()
    reg.register_indicator(
        IndicatorBlock(
            "gap",
            lambda df, period=1: df["close"].astype(float).pct_change(int(period)),
            (ParamSpec("period", 1.0, 1.0, 5.0, integer=True),),
            ParamSpec("threshold", 0.0, -0.05, 0.05),
        )
    )
    reg.register_comparator(Comparator("ge", lambda s, t: s >= t))
    spec = StrategySpec(name="custom", indicators=("gap",), rules=(Rule("gap", "ge", 0.0, 1),))
    signals = IndicatorStrategy(spec, blocks=reg).signals(ohlcv)
    assert signals.between(-1.0, 1.0).all()


def test_default_registry_contents() -> None:
    names = registry.indicator_names()
    assert {"momentum", "ema_ratio", "sma_ratio", "rsi", "macd_hist", "zscore"} <= set(names)
    assert {"gt", "lt", "abs_gt", "cross_above", "cross_below"} <= set(registry.comparator_names())
    # params are clipped into their legal range when computing
    block = registry.indicator("ema_ratio")
    out = block.compute(make_ohlcv(n=50), {"ema_ratio.period": 10_000.0})
    assert isinstance(out, pd.Series)


def test_param_spec_sampling_and_clipping(seed: int) -> None:
    import numpy as np

    spec = ParamSpec("period", 10.0, 5.0, 20.0, integer=True)
    rng = np.random.default_rng(seed)
    draws = [spec.sample(rng) for _ in range(20)]
    assert all(5.0 <= d <= 20.0 and d == round(d) for d in draws)
    assert spec.clip(3.2) == 5.0
    assert spec.clip(99.0) == 20.0
    with pytest.raises(ValueError):
        ParamSpec("bad", 1.0, 2.0, 3.0)
