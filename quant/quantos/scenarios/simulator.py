"""Scenario simulator (module 13, M4 scope).

``simulate(strategy_or_committee, scenario)`` runs a strategy — or a whole
:class:`~quantos.committee.committee.InvestmentCommittee` — through a named
scenario from the library and returns the standard
:class:`~quantos.backtest.engine.BacktestResult` (metrics + mandatory
baselines). Everything happens inside the vectorised backtest: **no broker,
no order, no capital** — synthetic bars in, research numbers out (invariant
I1). The whole run is a pure function of ``(subject, scenario, seed)`` (I8),
and positions are generated bar-by-bar from prefixes only (I2, inherited
from ``committee_signals`` and the engine's position lag).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd

from quantos.backtest.engine import BacktestResult, backtest, committee_signals
from quantos.backtest.metrics import HOURS_PER_YEAR
from quantos.committee.committee import InvestmentCommittee
from quantos.scenarios.library import Scenario, get_scenario

__all__ = ["SignalStrategy", "simulate"]


@runtime_checkable
class SignalStrategy(Protocol):
    """Anything that turns OHLCV into target positions in [-1, 1] (I7).

    The M5 ``Strategy`` contract satisfies this; so does any object exposing
    ``signals(ohlcv) -> Series``. Signals must be causal (I2).
    """

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Target position per bar, using only bars ≤ t (I2)."""
        ...


def _positions_for(
    subject: Any,
    ohlcv: pd.DataFrame,
    scenario: Scenario,
    warmup: int,
    step: int,
    context: dict[str, Any] | None,
) -> pd.Series:
    """Resolve a subject (committee / strategy / callable) into positions."""
    if isinstance(subject, InvestmentCommittee):
        return committee_signals(
            ohlcv,
            committee=subject,
            symbol=scenario.symbol,
            timeframe=scenario.timeframe,
            warmup=warmup,
            step=step,
            context=context,
        )
    if isinstance(subject, SignalStrategy):
        return subject.signals(ohlcv)
    if callable(subject):
        return subject(ohlcv)
    raise TypeError(
        f"cannot simulate a {type(subject).__name__}: expected an "
        "InvestmentCommittee, an object with signals(ohlcv), or a callable"
    )


def simulate(
    strategy_or_committee: Any,
    scenario: Scenario | str,
    seed: int | None = None,
    warmup: int = 60,
    step: int = 4,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    periods_per_year: float = HOURS_PER_YEAR,
    context: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run a strategy or committee through a named scenario (paper maths only, I1).

    Args:
        strategy_or_committee: an :class:`InvestmentCommittee` (deliberated
            bar-by-bar over prefixes, I2), an object with ``signals(ohlcv)``,
            or a plain ``callable(ohlcv) -> Series`` of target positions.
        scenario: a :class:`~quantos.scenarios.library.Scenario` or its name
            in the library (``"COVID_CRASH"``, ``"FTX"``, ...).
        seed: overrides the scenario's default path seed (I8).
        warmup: committee-only — bars to stay flat while indicators warm up.
        step: committee-only — deliberate every ``step`` bars.
        fee_bps: fee per unit of turnover.
        slippage_bps: slippage per unit of turnover.
        periods_per_year: annualisation factor for metrics.
        context: committee-only — extra deliberation context.

    Returns:
        The standard :class:`BacktestResult`; no broker and no capital are
        ever touched (I1).
    """
    if isinstance(scenario, str):
        scenario = get_scenario(scenario)
    ohlcv = scenario.generate(seed)
    positions = _positions_for(strategy_or_committee, ohlcv, scenario, warmup, step, context)
    return backtest(
        ohlcv,
        positions,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        periods_per_year=periods_per_year,
    )
