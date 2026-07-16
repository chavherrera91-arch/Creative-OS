"""Execution contracts and the safety gate.

These Protocols define how a broker, a pre-trade risk gate and an execution
engine interact — enough to wire the whole system today. But any attempt to build
a *live* execution engine raises :class:`LiveExecutionDisabled`. Paper trading is
the only execution path available in this phase.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from quantos.committee.decision import CommitteeDecision
from quantos.config import Settings, load_settings


class LiveExecutionDisabled(RuntimeError):
    """Raised on any attempt to route real orders. Intentional and load-bearing."""


@runtime_checkable
class Broker(Protocol):
    """Minimal broker contract. The paper broker satisfies this."""

    is_paper: bool

    def submit(
        self, symbol: str, side: str, quantity: float, price: float, **kwargs: Any
    ) -> Any:
        ...

    def equity(self, mark_price: float) -> float:
        ...


@runtime_checkable
class RiskGate(Protocol):
    """Pre-trade gate: the last line of defence before an order is sent."""

    def allow(self, decision: CommitteeDecision) -> bool:
        ...


@runtime_checkable
class ExecutionEngine(Protocol):
    def execute(self, decision: CommitteeDecision, price: float) -> Any:
        ...


class PaperExecutionEngine:
    """The only execution engine available now: routes to a paper broker."""

    def __init__(self, broker: Broker, risk_gate: RiskGate | None = None) -> None:
        if not getattr(broker, "is_paper", False):
            raise LiveExecutionDisabled(
                "Only paper brokers may be attached to an execution engine in this phase."
            )
        self.broker = broker
        self.risk_gate = risk_gate

    def execute(self, decision: CommitteeDecision, price: float) -> Any:
        if not decision.approved:
            return None
        if self.risk_gate and not self.risk_gate.allow(decision):
            return None
        target = decision.direction.sign  # 1 unit per direction (illustrative)
        return self.broker.target_position(  # type: ignore[attr-defined]
            decision.symbol,
            float(target),
            price,
            reason="; ".join(decision.reasons),
            context={"confidence": decision.confidence},
        )


def build_execution_engine(
    broker: Broker,
    *,
    live: bool = False,
    risk_gate: RiskGate | None = None,
    settings: Settings | None = None,
) -> PaperExecutionEngine:
    """Factory that refuses to build a live engine.

    ``live=True`` (or any config claiming to enable live trading) raises. This is
    the single choke point that keeps the platform research-only.
    """
    settings = settings or load_settings()
    if live or settings.live_trading_enabled:
        raise LiveExecutionDisabled(
            "Live execution is disabled in this phase. Paper trading only. "
            "Enabling real order routing is a deliberate, separate step."
        )
    return PaperExecutionEngine(broker, risk_gate=risk_gate)
