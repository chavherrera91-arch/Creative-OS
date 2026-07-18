"""WP-3.2 — forward test: deterministic (I8), no look-ahead (I2), paper only (I1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import make_ohlcv

from quantos.backtest.forward import ForwardTestResult, forward_test
from quantos.execution.interfaces import LiveExecutionDisabled
from quantos.paper.broker import PaperBroker


def run(df: pd.DataFrame, **kwargs: Any) -> ForwardTestResult:
    defaults: dict[str, Any] = {"warmup": 80, "step": 8}
    defaults.update(kwargs)
    return forward_test(None, df, **defaults)


class TestForwardTest:
    def test_produces_equity_curve_and_metrics(self) -> None:
        df = make_ohlcv(n=160, drift=0.003, vol=0.004, seed=7)
        result = run(df)
        assert len(result.equity) == len(df)
        assert float(result.equity.iloc[0]) == pytest.approx(1.0)
        assert np.isfinite(result.equity.to_numpy()).all()
        assert result.n_decisions == 10  # (160 - 80) / 8
        assert set(result.metrics) >= {"sharpe", "max_drawdown", "total_return"}
        assert {"strategy", "buy_and_hold", "random"} <= set(result.baselines)

    def test_trades_carry_full_dossier(self) -> None:
        """I4: every paper fill records the decision that caused it."""
        from quantos.config import Settings

        df = make_ohlcv(n=160, drift=0.004, vol=0.003, seed=7)
        # An OHLCV-only snapshot leaves the data-hungry analysts abstaining
        # (I3), so the evidence bar is lowered to let the trend trade.
        result = run(df, settings=Settings(confidence_threshold=0.15, min_agreement=0.3))
        assert result.n_trades > 0  # the uptrend convinces the committee
        assert all(d["direction"] == "LONG" for d in result.decisions)
        for trade in result.trades:
            assert trade.dossier["direction"] == "LONG"
            assert "risk" in trade.dossier

    def test_deterministic(self, assert_reproducible: Callable[..., Any]) -> None:
        """I8: same committee + same stream => identical result."""
        df = make_ohlcv(n=140, drift=0.003, vol=0.004, seed=7)
        assert_reproducible(lambda: run(df).as_dict())

    def test_no_look_ahead(self) -> None:
        """I2: perturbing future bars cannot change the past equity path."""
        df = make_ohlcv(n=160, drift=0.003, vol=0.004, seed=7)
        cut = 120
        perturbed = df.copy()
        perturbed.iloc[cut:, :] *= 1.5  # violent future shock

        base = run(df)
        shocked = run(perturbed)
        pd.testing.assert_series_equal(base.equity.iloc[:cut], shocked.equity.iloc[:cut])

    def test_only_paper_brokers_accepted(self) -> None:
        """I1: a non-paper broker is refused outright."""

        class SneakyLiveBroker:
            is_paper = False

            def submit(self, *a: Any, **k: Any) -> Any: ...
            def equity(self, prices: dict[str, float] | None = None) -> float:
                return 0.0

        df = make_ohlcv(n=120)
        with pytest.raises(LiveExecutionDisabled):
            forward_test(None, df, warmup=80, broker=SneakyLiveBroker())

    def test_flat_committee_keeps_equity_flat(self) -> None:
        """No approvals -> no trades -> equity pinned at 1.0."""
        from quantos.committee.committee import default_committee

        committee = default_committee()
        committee.confidence_model.threshold = 1.01  # unreachable
        df = make_ohlcv(n=140, drift=0.003, vol=0.004, seed=7)
        result = forward_test(committee, df, warmup=80, step=8)
        assert result.n_trades == 0
        assert (result.equity == 1.0).all()

    def test_short_stream_rejected(self) -> None:
        with pytest.raises(ValueError):
            forward_test(None, make_ohlcv(n=50), warmup=80)

    def test_uses_supplied_broker_and_settings(self) -> None:
        from quantos.config import Settings

        broker = PaperBroker(cash=10_000.0, fee_bps=0.0, slippage_bps=0.0)
        df = make_ohlcv(n=140, drift=0.004, vol=0.003, seed=7)
        result = forward_test(
            None, df, warmup=80, step=8, broker=broker,
            settings=Settings(
                max_position_fraction=0.1, confidence_threshold=0.15, min_agreement=0.3
            ),
        )
        assert result.initial_cash == pytest.approx(10_000.0)
        for trade in result.trades:
            # position never exceeds the configured fraction of equity
            assert abs(trade.position_after * trade.fill_price) <= 0.1 * trade.equity_after * 1.05
