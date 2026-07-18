"""WP-3.4 — execution realism: CostModel fills, back-compatible broker + backtest."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.backtest.engine import backtest
from quantos.execution.costs import (
    CostModel,
    Fill,
    FlatCostModel,
    ImpactCostModel,
    ZeroCostModel,
)
from quantos.paper.broker import PaperBroker


class TestFillAndModels:
    def test_zero_cost_fill_is_frictionless(self) -> None:
        fill = ZeroCostModel().fill("buy", 2.0, 100.0)
        assert fill.fill_price == 100.0
        assert fill.fee == 0.0
        assert fill.total_cost == 0.0
        json.dumps(fill.as_dict())

    def test_flat_model_matches_m1_arithmetic(self) -> None:
        """FlatCostModel reproduces the original PaperBroker fill bit-for-bit."""
        fill = FlatCostModel(fee_bps=10.0, slippage_bps=5.0).fill("buy", 2.0, 100.0)
        slip = 100.0 * 5.0 / 10_000.0
        assert fill.fill_price == 100.0 + slip  # adverse for a buy
        assert fill.notional == 2.0 * fill.fill_price
        assert fill.fee == fill.notional * 10.0 / 10_000.0
        sell = FlatCostModel(fee_bps=10.0, slippage_bps=5.0).fill("sell", 2.0, 100.0)
        assert sell.fill_price == 100.0 - slip  # adverse for a sell

    def test_flat_model_is_size_independent(self) -> None:
        model = FlatCostModel()
        small, large = model.fill("buy", 1.0, 100.0), model.fill("buy", 1000.0, 100.0)
        assert small.fill_price == large.fill_price

    def test_larger_orders_incur_more_impact(self) -> None:
        """Acceptance: size-dependent slippage/impact."""
        model = ImpactCostModel(ref_depth_notional=100_000.0)
        small = model.fill("buy", 1.0, 100.0)
        large = model.fill("buy", 1000.0, 100.0)
        assert large.impact > small.impact > 0.0
        assert large.fill_price > small.fill_price
        # per-unit cost also grows: the square-root law is convex in notional
        assert large.total_cost / large.qty > small.total_cost / small.qty

    def test_book_depth_softens_impact(self) -> None:
        model = ImpactCostModel(ref_depth_notional=100_000.0)
        thin = model.fill("buy", 100.0, 100.0, book={"depth_notional": 10_000.0})
        deep = model.fill("buy", 100.0, 100.0, book={"depth_notional": 10_000_000.0})
        assert thin.impact > deep.impact

    def test_stressed_regime_costs_more(self) -> None:
        model = ImpactCostModel()
        calm = model.fill("buy", 10.0, 100.0)
        crisis = model.fill("buy", 10.0, 100.0, regime={"label": "CRISIS"})
        assert crisis.total_cost > calm.total_cost

    def test_models_satisfy_protocol(self) -> None:
        for model in (ZeroCostModel(), FlatCostModel(), ImpactCostModel()):
            assert isinstance(model, CostModel)

    def test_invalid_orders_rejected(self) -> None:
        model = FlatCostModel()
        with pytest.raises(ValueError):
            model.fill("hold", 1.0, 100.0)
        with pytest.raises(ValueError):
            model.fill("buy", 0.0, 100.0)
        with pytest.raises(ValueError):
            model.fill("buy", 1.0, -1.0)

    def test_deterministic(self, assert_reproducible: Callable[..., Any]) -> None:
        model = ImpactCostModel()
        assert_reproducible(lambda: model.fill("buy", 42.0, 123.45).as_dict())


class TestPaperBrokerRouting:
    def test_default_broker_unchanged(self) -> None:
        """Back-compat: no cost_model => the original flat arithmetic."""
        old_style = PaperBroker(cash=10_000.0, fee_bps=10.0, slippage_bps=5.0)
        record = old_style.submit("BTC/USDT", "buy", 1.0, 100.0)
        slip = 100.0 * 5.0 / 10_000.0
        assert record.fill_price == pytest.approx(100.0 + slip)
        assert record.fee == pytest.approx(record.notional * 10.0 / 10_000.0)

    def test_explicit_flat_model_matches_default(self) -> None:
        a = PaperBroker(cash=10_000.0, fee_bps=10.0, slippage_bps=5.0)
        b = PaperBroker(cash=10_000.0, cost_model=FlatCostModel(fee_bps=10.0, slippage_bps=5.0))
        ra = a.submit("BTC/USDT", "buy", 2.0, 100.0)
        rb = b.submit("BTC/USDT", "buy", 2.0, 100.0)
        assert ra.fill_price == rb.fill_price
        assert ra.fee == rb.fee
        assert ra.cash_after == rb.cash_after

    def test_impact_model_worsens_large_fills(self) -> None:
        broker = PaperBroker(cash=1e9, cost_model=ImpactCostModel(ref_depth_notional=100_000.0))
        small = broker.submit("BTC/USDT", "buy", 1.0, 100.0)
        large = broker.submit("BTC/USDT", "buy", 10_000.0, 100.0)
        assert large.fill_price > small.fill_price

    def test_regime_context_flows_through(self) -> None:
        broker = PaperBroker(cash=1e6, cost_model=ImpactCostModel())
        calm = broker.submit("BTC/USDT", "buy", 1.0, 100.0)
        stressed = broker.submit("BTC/USDT", "buy", 1.0, 100.0, regime={"label": "CRISIS"})
        assert stressed.fill_price > calm.fill_price


class TestBacktestRouting:
    @staticmethod
    def positions(ohlcv: pd.DataFrame) -> pd.Series:
        rng = np.random.default_rng(3)
        return pd.Series(rng.integers(-1, 2, size=len(ohlcv)).astype(float), index=ohlcv.index)

    def test_zero_cost_model_reproduces_costfree_backtest(self) -> None:
        """Acceptance: ZeroCostModel == the old engine with zero bps."""
        ohlcv = make_ohlcv(n=250, seed=42)
        pos = self.positions(ohlcv)
        flat_free = backtest(ohlcv, pos, fee_bps=0.0, slippage_bps=0.0)
        model_free = backtest(ohlcv, pos, cost_model=ZeroCostModel())
        pd.testing.assert_series_equal(flat_free.returns, model_free.returns)
        assert flat_free.metrics == model_free.metrics

    def test_flat_cost_model_reproduces_flat_backtest(self) -> None:
        """FlatCostModel matches the flat-bps path.

        The model charges the fee on the *filled* notional (price after
        slippage), so equality is to within the fee*slippage cross-term:
        turnover * fee_bps * slippage_bps / 1e8 <= 2 * 10 * 5 / 1e8 = 1e-6.
        """
        ohlcv = make_ohlcv(n=250, seed=42)
        pos = self.positions(ohlcv)
        flat = backtest(ohlcv, pos, fee_bps=10.0, slippage_bps=5.0)
        model = backtest(
            ohlcv, pos, cost_model=FlatCostModel(fee_bps=10.0, slippage_bps=5.0)
        )
        assert np.max(np.abs(flat.returns.to_numpy() - model.returns.to_numpy())) <= 1.01e-6
        assert flat.n_trades == model.n_trades

    def test_impact_model_costs_more_than_flat(self) -> None:
        ohlcv = make_ohlcv(n=250, seed=42)
        pos = self.positions(ohlcv)
        flat = backtest(ohlcv, pos, cost_model=FlatCostModel(fee_bps=10.0, slippage_bps=5.0))
        impact = backtest(
            ohlcv,
            pos,
            cost_model=ImpactCostModel(
                fee_bps=10.0, slippage_bps=5.0, ref_depth_notional=50_000.0
            ),
            capital=1_000_000.0,  # big orders into thin depth
        )
        assert impact.metrics["total_return"] < flat.metrics["total_return"]

    def test_no_look_ahead_with_cost_model(self) -> None:
        """I2: perturbing future bars cannot change earlier net returns."""
        ohlcv = make_ohlcv(n=250, seed=42)
        pos = self.positions(ohlcv)
        cut = 200
        shocked = ohlcv.copy()
        shocked.iloc[cut:, :] *= 3.0
        base = backtest(ohlcv, pos, cost_model=ImpactCostModel())
        after = backtest(shocked, pos, cost_model=ImpactCostModel())
        pd.testing.assert_series_equal(base.returns.iloc[:cut], after.returns.iloc[:cut])

    def test_deterministic(self, assert_reproducible: Callable[..., Any]) -> None:
        ohlcv = make_ohlcv(n=200, seed=42)
        pos = self.positions(ohlcv)
        assert_reproducible(lambda: backtest(ohlcv, pos, cost_model=ImpactCostModel()).as_dict())


def test_fill_dataclass_is_frozen() -> None:
    fill = ZeroCostModel().fill("buy", 1.0, 100.0)
    with pytest.raises(AttributeError):
        fill.fee = 1.0  # type: ignore[misc]
    assert isinstance(fill, Fill)
