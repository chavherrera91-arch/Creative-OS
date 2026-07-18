"""Forward test: the out-of-sample simulation harness (module 7, M3 scope).

The bridge between walk-forward analysis and paper trading in the validation
funnel: a snapshot is stepped forward **bar by bar** — at each decision bar the
committee sees only the bars revealed so far (invariant I2) — and every stance
is executed against the paper broker, producing a marked-to-market equity
curve. Only paper brokers are accepted (I1); the whole run is a pure function
of ``(committee, data, parameters)`` (I8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.backtest.baselines import vs_baselines
from quantos.backtest.metrics import HOURS_PER_YEAR, summarize
from quantos.committee.committee import InvestmentCommittee, default_committee
from quantos.config import Settings
from quantos.data.models import MarketSnapshot
from quantos.execution.interfaces import Broker, LiveExecutionDisabled
from quantos.paper.broker import PaperBroker, TradeRecord

__all__ = ["ForwardTestResult", "forward_test"]


@dataclass
class ForwardTestResult:
    """Everything a forward-test run produced.

    Attributes:
        equity: marked-to-market equity curve normalised to start at 1.0.
        returns: per-bar simple returns of that equity curve.
        metrics: standard metrics dict over ``returns``.
        baselines: metrics vs buy-and-hold and the seeded random baseline.
        decisions: one summary dict per committee deliberation (I4).
        trades: every paper fill, with its full dossier.
        n_decisions: number of deliberations run.
        n_trades: number of paper fills executed.
        initial_cash: paper starting equity.
        final_equity: ending account equity in cash terms.
    """

    equity: pd.Series
    returns: pd.Series
    metrics: dict[str, float]
    baselines: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    n_decisions: int = 0
    n_trades: int = 0
    initial_cash: float = 0.0
    final_equity: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (series omitted, records kept)."""
        return {
            "metrics": dict(self.metrics),
            "baselines": dict(self.baselines),
            "decisions": [dict(d) for d in self.decisions],
            "n_decisions": self.n_decisions,
            "n_trades": self.n_trades,
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "final_equity_multiple": (
                float(self.equity.iloc[-1]) if len(self.equity) else 1.0
            ),
        }


def _decision_summary(decision: Any, target_fraction: float) -> dict[str, Any]:
    """Compact, JSON-serialisable record of one deliberation (I4)."""
    return {
        "as_of": decision.as_of,
        "direction": decision.direction.value,
        "approved": decision.approved,
        "confidence": decision.confidence,
        "blocked_by_risk": decision.blocked_by_risk,
        "target_fraction": target_fraction,
    }


def forward_test(
    committee: InvestmentCommittee | None,
    ohlcv_stream: pd.DataFrame,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    warmup: int = 60,
    step: int = 1,
    broker: Broker | None = None,
    settings: Settings | None = None,
    context: dict[str, Any] | None = None,
    rebalance_threshold: float = 0.05,
    periods_per_year: float = HOURS_PER_YEAR,
    baseline_seed: int = 7,
) -> ForwardTestResult:
    """Step a snapshot forward bar-by-bar, feeding the paper engine.

    At each decision bar the committee deliberates over **only the bars
    revealed so far** (I2); an approved stance is converted to a target
    position fraction (``max_position_fraction * confidence``, signed) and the
    paper broker is rebalanced towards it at that bar's close. Equity is
    marked at every bar's close.

    Args:
        committee: committee to consult; the default bench when None.
        ohlcv_stream: the full bar history, revealed strictly bar by bar.
        symbol: symbol label for the snapshots and the paper book.
        timeframe: timeframe label for the snapshots.
        warmup: bars to stay flat while indicators warm up.
        step: deliberate every ``step`` bars (the stance carries in between).
        broker: destination broker; a fresh :class:`PaperBroker` by default.
            **Must be a paper broker** (I1).
        settings: platform settings (cash, fees, max position fraction).
        context: optional deliberation context forwarded to the committee.
        rebalance_threshold: minimum change in target fraction of equity
            before a rebalancing order is placed (suppresses fee churn).
        periods_per_year: annualisation factor for metrics.
        baseline_seed: seed for the random baseline (I8).

    Returns:
        A :class:`ForwardTestResult` with the equity curve, metrics,
        mandatory baselines, decision summaries and paper trades.

    Raises:
        LiveExecutionDisabled: if ``broker`` is not a paper broker (I1).
        ValueError: if the stream is shorter than the warmup.
    """
    if len(ohlcv_stream) <= warmup:
        raise ValueError(f"need more than warmup={warmup} bars, got {len(ohlcv_stream)}")
    settings = settings or Settings()
    committee = committee or default_committee(settings)
    if broker is None:
        broker = PaperBroker(
            cash=settings.initial_cash,
            fee_bps=settings.fee_bps,
            slippage_bps=settings.slippage_bps,
        )
    if getattr(broker, "is_paper", False) is not True:
        raise LiveExecutionDisabled(
            f"broker {type(broker).__name__} is not a paper broker — refused (I1)"
        )

    initial_cash = broker.equity()
    close = ohlcv_stream["close"].astype(float)
    equity_values: list[float] = []
    decisions: list[dict[str, Any]] = []
    target_fraction = 0.0

    for i in range(len(ohlcv_stream)):
        price = float(close.iloc[i])
        if i >= warmup and (i - warmup) % step == 0:
            visible = ohlcv_stream.iloc[: i + 1]  # only the bars revealed so far (I2)
            snapshot = MarketSnapshot(symbol=symbol, timeframe=timeframe, ohlcv=visible)
            decision = committee.deliberate(snapshot, context)
            if decision.approved:
                target_fraction = (
                    float(decision.direction.sign)
                    * settings.max_position_fraction
                    * decision.confidence
                )
            else:
                target_fraction = 0.0
            decisions.append(_decision_summary(decision, target_fraction))

            equity_now = broker.equity({symbol: price})
            held = getattr(broker, "position", lambda _s: 0.0)(symbol)
            held_fraction = held * price / equity_now if equity_now > 0 else 0.0
            if abs(target_fraction - held_fraction) > rebalance_threshold:
                delta_qty = (target_fraction * equity_now / price) - held
                if abs(delta_qty) * price > 0:
                    broker.submit(
                        symbol=symbol,
                        side="buy" if delta_qty > 0 else "sell",
                        qty=abs(delta_qty),
                        price=price,
                        as_of=decision.as_of,
                        dossier=decision.as_dict(),
                    )
        equity_values.append(broker.equity({symbol: price}))

    equity = pd.Series(equity_values, index=ohlcv_stream.index) / initial_cash
    returns = equity.pct_change().fillna(0.0)
    trades = list(getattr(broker, "trades", []))
    return ForwardTestResult(
        equity=equity,
        returns=returns,
        metrics=summarize(returns, periods_per_year),
        baselines=vs_baselines(
            returns, close, seed=baseline_seed, periods_per_year=periods_per_year
        ),
        decisions=decisions,
        trades=trades,
        n_decisions=len(decisions),
        n_trades=len(trades),
        initial_cash=initial_cash,
        final_equity=broker.equity({symbol: float(close.iloc[-1])}),
    )
