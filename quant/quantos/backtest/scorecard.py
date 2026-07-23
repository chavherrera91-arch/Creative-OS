"""Strategy Score — one honest report card, not a single flattering number.

A good strategy is not "it won 120%". It is a **consistent statistical edge
across many trades and market conditions**. This module consolidates the
platform's existing honesty tools — cost-charged backtest, out-of-sample
walk-forward with the Deflated Sharpe, Monte Carlo, regime robustness and a
parameter-sensitivity probe — into a single weighted score (0–100), a per-metric
pass/fail card, and a verdict (``REJECTED`` → ``READY FOR PAPER TRADING``).

Every check reads only realised numbers (I4), charges costs (module 26), and is
deterministic for a given ``(strategy, data, seed)`` (I8). Nothing here trades
real capital (I1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from quantos.backtest.engine import BacktestResult, backtest
from quantos.backtest.metrics import summarize, total_return
from quantos.backtest.monte_carlo import monte_carlo
from quantos.backtest.walk_forward import walk_forward
from quantos.scenarios.library import get_scenario, scenario_names
from quantos.strategy.base import IndicatorStrategy, StrategySpec

__all__ = ["Check", "Scorecard", "evaluate"]


@dataclass
class Check:
    """One graded metric on the report card.

    Attributes:
        name: metric name.
        value: measured value (display string).
        target: the bar it had to clear (display string).
        passed: whether it cleared the bar.
        weight: its weight in the 0–100 score.
    """

    name: str
    value: str
    target: str
    passed: bool
    weight: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "metrica": self.name,
            "valor": self.value,
            "objetivo": self.target,
            "cumple": "✅" if self.passed else "❌",
            "peso": self.weight,
        }


@dataclass
class Scorecard:
    """The full report: graded checks, a 0–100 score and a verdict (I4)."""

    checks: list[Check] = field(default_factory=list)
    score: int = 0
    verdict: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "score": self.score,
            "verdict": self.verdict,
            "checks": [c.as_dict() for c in self.checks],
        }


def _expectancy(returns: pd.Series) -> float:
    """Average per-bar return in loss-units (positive ⇒ positive expectancy)."""
    clean = returns.dropna()
    losses = clean[clean < 0]
    denom = abs(float(losses.mean())) if len(losses) else 1.0
    return float(clean.mean()) / (denom or 1.0)


def _consistency(returns: pd.Series, buckets: int = 6) -> float:
    """Fraction of equal time-buckets that ended positive (timeframe-agnostic)."""
    clean = returns.dropna().to_numpy()
    if len(clean) < buckets:
        return 1.0 if float(clean.sum()) > 0 else 0.0
    chunks = np.array_split(clean, buckets)
    return float(np.mean([chunk.sum() > 0 for chunk in chunks]))


def _regime_robustness(
    strategy: Any, scenarios: list[str], seed: int, fee_bps: float, slippage_bps: float
) -> tuple[bool, float]:
    """Fraction of market regimes the strategy stays positive in."""
    wins = 0
    for name in scenarios:
        ohlcv = get_scenario(name).generate(seed)
        result = backtest(
            ohlcv, strategy.signals(ohlcv), fee_bps=fee_bps, slippage_bps=slippage_bps
        )
        if total_return(result.returns) > 0:
            wins += 1
    frac = wins / len(scenarios) if scenarios else 0.0
    return frac >= 0.6, frac


def _sensitivity(
    strategy: Any, ohlcv: pd.DataFrame, fee_bps: float, slippage_bps: float
) -> tuple[bool, float]:
    """Does the edge survive small (±10%) parameter changes? (anti-overfit)."""
    spec = getattr(strategy, "spec", None)
    if not isinstance(spec, StrategySpec) or not spec.params:
        return True, 1.0  # nothing to perturb → trivially robust
    survived = 0
    variants = 0
    for factor in (0.9, 1.1):
        params = {
            k: (v * factor if isinstance(v, (int, float)) else v) for k, v in spec.params.items()
        }
        variant = StrategySpec(
            name=spec.name,
            version=spec.version,
            family=spec.family,
            indicators=spec.indicators,
            rules=spec.rules,
            params=params,
            target_regimes=spec.target_regimes,
        )
        try:
            result = backtest(
                ohlcv,
                IndicatorStrategy(variant).signals(ohlcv),
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
            )
        except Exception:  # noqa: BLE001 - a broken variant just counts as a miss
            variants += 1
            continue
        variants += 1
        if total_return(result.returns) > 0:
            survived += 1
    frac = survived / variants if variants else 1.0
    return frac >= 0.5, frac


def _verdict(score: int) -> str:
    if score >= 85:
        return "READY FOR PAPER TRADING"
    if score >= 70:
        return "PROMETEDORA — necesita más pruebas"
    if score >= 50:
        return "NEEDS WORK"
    return "REJECTED"


def evaluate(
    strategy: Any,
    ohlcv: pd.DataFrame,
    *,
    n_trials: int = 1,
    scenarios: list[str] | None = None,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    seed: int = 7,
) -> Scorecard:
    """Grade a strategy across the full honesty battery; return its report card.

    Args:
        strategy: object with ``signals(ohlcv)`` (and optionally ``.spec``).
        ohlcv: the primary bar history to grade on (costs charged).
        n_trials: strategies examined during selection — deflates the Sharpe (I9).
        scenarios: regime scenarios for robustness (the default library when None).
        fee_bps / slippage_bps: trading costs charged in every backtest.
        seed: seed for Monte Carlo and scenario generation (I8).
    """
    scenarios = scenarios if scenarios is not None else list(scenario_names())
    result: BacktestResult = backtest(
        ohlcv, strategy.signals(ohlcv), fee_bps=fee_bps, slippage_bps=slippage_bps
    )
    metrics = summarize(result.returns)
    ret = result.returns

    mc = monte_carlo(ret, n_sims=300, seed=seed)
    worst_dd = float(mc.max_drawdown_percentiles.get("p05", 0.0))

    def signal_fn(prefix: pd.DataFrame) -> pd.Series:
        return strategy.signals(prefix)

    try:
        wf = walk_forward(
            ohlcv, signal_fn, n_trials=max(n_trials, 1), fee_bps=fee_bps, slippage_bps=slippage_bps
        )
        oos_dsr = float(wf.validation.get("deflated_sharpe", 0.0))
        oos_sharpe = float(wf.oos_metrics.get("sharpe", 0.0))
    except Exception:  # noqa: BLE001 - too short a sample: OOS simply not proven
        oos_dsr, oos_sharpe = 0.0, 0.0

    regime_ok, regime_frac = _regime_robustness(strategy, scenarios, seed, fee_bps, slippage_bps)
    sens_ok, sens_frac = _sensitivity(strategy, ohlcv, fee_bps, slippage_bps)

    pf = metrics["profit_factor"]
    dd = metrics["max_drawdown"]
    recovery = total_return(ret) / abs(dd) if dd < 0 else float("inf")
    expectancy = _expectancy(ret)
    consistency = _consistency(ret)

    checks = [
        Check(
            "Rentabilidad", f"{metrics['total_return']:+.1%}", "> 0", metrics["total_return"] > 0, 6
        ),
        Check("Profit Factor", f"{pf:.2f}", "> 1.5", pf > 1.5, 12),
        Check("Sharpe", f"{metrics['sharpe']:.2f}", "> 1.5", metrics["sharpe"] > 1.5, 12),
        Check("Sortino", f"{metrics['sortino']:.2f}", "> 2.0", metrics["sortino"] > 2.0, 8),
        Check("Max Drawdown", f"{dd:.1%}", "> -15%", dd > -0.15, 12),
        Check("Expectancy", f"{expectancy:+.2f}R", "> 0", expectancy > 0, 8),
        Check("Recovery Factor", f"{recovery:.2f}", "> 2", recovery > 2.0, 6),
        Check("Operaciones", f"{result.n_trades}", "≥ 100", result.n_trades >= 100, 8),
        Check("Consistencia", f"{consistency:.0%}", "> 50%", consistency > 0.5, 8),
        Check(
            "Out-of-Sample (DSR)", f"{oos_dsr:.0%}", "≥ 60%", oos_dsr >= 0.6 and oos_sharpe > 0, 12
        ),
        Check("Monte Carlo (peor DD)", f"{worst_dd:.1%}", "> -30%", worst_dd > -0.30, 8),
        Check("Robustez por régimen", f"{regime_frac:.0%}", "≥ 60%", regime_ok, 12),
        Check("Sensibilidad", f"{sens_frac:.0%}", "≥ 50%", sens_ok, 8),
    ]
    total_weight = sum(c.weight for c in checks)
    earned = sum(c.weight for c in checks if c.passed)
    score = round(100 * earned / total_weight) if total_weight else 0
    return Scorecard(checks=checks, score=score, verdict=_verdict(score))
