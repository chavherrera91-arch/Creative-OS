"""A simulated (paper) broker.

Tracks cash, a single-symbol position and equity, applying fees and slippage on
each fill. Every fill produces a :class:`TradeRecord` — the "expediente" from the
continuous-learning vision: the full context of why the trade happened, so it can
later be audited. This class implements the same ``Broker`` protocol the future
live engine will, but it can never move real money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PaperFill:
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    price: float
    fee: float
    timestamp: datetime


@dataclass
class TradeRecord:
    """One trade's full dossier for later audit / continuous learning."""

    fill: PaperFill
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.fill.timestamp.isoformat(),
            "symbol": self.fill.symbol,
            "side": self.fill.side,
            "quantity": round(self.fill.quantity, 8),
            "price": round(self.fill.price, 8),
            "fee": round(self.fill.fee, 8),
            "reason": self.reason,
            "context": self.context,
        }


class PaperBroker:
    is_paper = True  # explicit, checked by the execution layer

    def __init__(
        self,
        cash: float = 10_000.0,
        fee_rate: float = 0.0004,
        slippage: float = 0.0005,
    ) -> None:
        self.initial_cash = cash
        self.cash = cash
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.position = 0.0  # units of the asset (can be negative = short)
        self.symbol: str | None = None
        self.trades: list[TradeRecord] = []

    # -- Broker protocol ------------------------------------------------------
    def submit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        *,
        reason: str = "",
        context: dict[str, Any] | None = None,
    ) -> TradeRecord:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        signed = 1.0 if side == "buy" else -1.0
        fill_price = price * (1.0 + signed * self.slippage)  # slippage against us
        notional = fill_price * quantity
        fee = notional * self.fee_rate

        self.cash -= signed * notional + fee
        self.position += signed * quantity
        self.symbol = symbol

        record = TradeRecord(
            fill=PaperFill(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fill_price,
                fee=fee,
                timestamp=datetime.now(timezone.utc),
            ),
            reason=reason,
            context=context or {},
        )
        self.trades.append(record)
        return record

    def target_position(
        self, symbol: str, target_units: float, price: float, **kwargs
    ) -> TradeRecord | None:
        """Trade toward a target position (units). Returns the fill, if any."""
        delta = target_units - self.position
        if abs(delta) < 1e-12:
            return None
        side = "buy" if delta > 0 else "sell"
        return self.submit(symbol, side, abs(delta), price, **kwargs)

    def equity(self, mark_price: float) -> float:
        return self.cash + self.position * mark_price

    def pnl(self, mark_price: float) -> float:
        return self.equity(mark_price) - self.initial_cash

    def blotter(self) -> list[dict[str, Any]]:
        return [t.as_dict() for t in self.trades]
