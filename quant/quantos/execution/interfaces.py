"""Execution ports and the hard I1 guarantee.

``Broker``, ``RiskGate`` and ``ExecutionEngine`` are the Protocols a future
engine must satisfy (invariant I7) — but **no code path places a live order**
(invariant I1):

- :func:`build_execution_engine` raises :class:`LiveExecutionDisabled` the
  moment ``live=True`` is requested;
- :class:`PaperExecutionEngine` refuses any broker whose ``is_paper`` flag is
  not ``True``.

Both guards are covered by tests; weakening either is a failed build by
definition (ARCHITECTURE §0).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from quantos.committee.decision import CommitteeDecision
from quantos.config import Settings
from quantos.paper.broker import PaperBroker, TradeRecord
from quantos.sizing.base import PositionSizer

__all__ = [
    "Broker",
    "DefaultRiskGate",
    "ExecutionEngine",
    "LiveExecutionDisabled",
    "PaperExecutionEngine",
    "RiskGate",
    "build_execution_engine",
]


class LiveExecutionDisabled(RuntimeError):
    """Raised whenever anything attempts to route real capital (I1)."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "Live execution is hard-disabled: quantos is a research platform "
            "and never places real orders (invariant I1)."
        )


@runtime_checkable
class Broker(Protocol):
    """Order destination. Only paper implementations are ever accepted."""

    is_paper: bool

    def submit(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        as_of: str = "",
        dossier: dict[str, Any] | None = None,
    ) -> TradeRecord:
        """Fill an order and return its trade record."""
        ...

    def equity(self, prices: dict[str, float] | None = None) -> float:
        """Current account equity."""
        ...


@runtime_checkable
class RiskGate(Protocol):
    """Final pre-trade check between a decision and the broker."""

    def allow(self, decision: CommitteeDecision) -> bool:
        """True only when the decision may be executed."""
        ...


@runtime_checkable
class ExecutionEngine(Protocol):
    """Routes an approved decision to a broker."""

    def execute(
        self, decision: CommitteeDecision, price: float | None = None
    ) -> TradeRecord | None:
        """Execute a decision; None when nothing was traded."""
        ...


class DefaultRiskGate:
    """Defence in depth: re-checks approval and the risk veto (I5)."""

    def allow(self, decision: CommitteeDecision) -> bool:
        """Only approved, un-vetoed, non-FLAT decisions pass."""
        return decision.approved and not decision.blocked_by_risk and decision.direction.sign != 0


class PaperExecutionEngine:
    """Executes committee decisions against a paper broker — and only paper.

    Sizing: with a :class:`~quantos.sizing.base.PositionSizer` (module 26,
    M3) the engine consults it for the position fraction; without one it uses
    the simple M1 rule ``max_position_fraction * confidence``. Either way the
    fraction is **clamped to ``settings.max_position_fraction``** — the Risk
    Manager's limit is absolute and a sizer can never breach it (I5).
    """

    def __init__(
        self,
        broker: Broker | None = None,
        risk_gate: RiskGate | None = None,
        settings: Settings | None = None,
        sizer: PositionSizer | None = None,
    ) -> None:
        """
        Args:
            broker: destination broker; a fresh :class:`PaperBroker` by default.
            risk_gate: optional gate; :class:`DefaultRiskGate` by default.
            settings: platform settings (cash, fees, max position fraction).
            sizer: optional position sizer the engine consults (module 26).

        Raises:
            LiveExecutionDisabled: if ``broker`` is not a paper broker (I1).
        """
        self.settings = settings or Settings()
        if broker is None:
            broker = PaperBroker(
                cash=self.settings.initial_cash,
                fee_bps=self.settings.fee_bps,
                slippage_bps=self.settings.slippage_bps,
            )
        if getattr(broker, "is_paper", False) is not True:
            raise LiveExecutionDisabled(
                f"broker {type(broker).__name__} is not a paper broker — refused (I1)"
            )
        self.broker = broker
        self.risk_gate = risk_gate or DefaultRiskGate()
        self.sizer = sizer

    def execute(
        self,
        decision: CommitteeDecision,
        price: float | None = None,
        vol: float | None = None,
        corr: Mapping[str, float] | float | None = None,
    ) -> TradeRecord | None:
        """Route a decision through the risk gate to the paper broker.

        Args:
            decision: the committee's call.
            price: execution reference price; the decision's price by default.
            vol: annualised asset volatility forwarded to the sizer.
            corr: correlation(s) with the book forwarded to the sizer.

        Returns:
            The fill's :class:`TradeRecord`, or None when the gate held it back.
        """
        if not self.risk_gate.allow(decision):
            return None
        fill_price = decision.price if price is None else price
        equity = self.broker.equity({decision.symbol: fill_price})
        if self.sizer is not None:
            fraction = abs(
                self.sizer.size(decision, portfolio={"equity": equity}, vol=vol, corr=corr)
            )
        else:
            fraction = self.settings.max_position_fraction * decision.confidence
        # Defence in depth: whatever the sizer says, the risk limit wins (I5).
        fraction = min(fraction, self.settings.max_position_fraction)
        notional = equity * fraction
        qty = notional / fill_price
        if qty <= 0:
            return None
        side = "buy" if decision.direction.sign > 0 else "sell"
        return self.broker.submit(
            symbol=decision.symbol,
            side=side,
            qty=qty,
            price=fill_price,
            as_of=decision.as_of,
            dossier=decision.as_dict(),
        )


def build_execution_engine(
    live: bool = False,
    broker: Broker | None = None,
    risk_gate: RiskGate | None = None,
    settings: Settings | None = None,
    sizer: PositionSizer | None = None,
) -> ExecutionEngine:
    """The only factory for execution engines — and it refuses live (I1).

    Args:
        live: requesting a live engine raises, unconditionally.
        broker: optional broker (must be paper).
        risk_gate: optional gate; :class:`DefaultRiskGate` by default.
        settings: platform settings.
        sizer: optional position sizer the engine consults (module 26).

    Returns:
        A :class:`PaperExecutionEngine`.

    Raises:
        LiveExecutionDisabled: when ``live=True`` or ``broker`` is not paper.
    """
    if live:
        raise LiveExecutionDisabled()
    return PaperExecutionEngine(broker=broker, risk_gate=risk_gate, settings=settings, sizer=sizer)
