"""Paper broker: simulated fills with fees, slippage and a per-trade dossier.

``PaperBroker`` is the **only** broker that accepts orders anywhere in the
platform (invariant I1: ``is_paper`` is True and the execution layer rejects
anything else). Every fill produces a :class:`TradeRecord` — the per-trade
"expediente" carrying the full decision record that caused it (I4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantos.execution.costs import CostModel, FlatCostModel

__all__ = ["PaperBroker", "TradeRecord"]

BUY = "buy"
SELL = "sell"


@dataclass
class TradeRecord:
    """One simulated fill plus its complete audit trail.

    Attributes:
        trade_id: sequential id within this broker session.
        symbol: market traded.
        side: ``"buy"`` or ``"sell"``.
        qty: quantity filled (always positive; side carries the sign).
        requested_price: price at decision time.
        fill_price: price after slippage.
        fee: fee charged on the notional.
        notional: ``qty * fill_price``.
        position_after: signed position in the symbol after the fill.
        cash_after: cash after the fill.
        equity_after: cash + position marked at the fill price.
        as_of: bar timestamp of the decision (never a wall clock, I8).
        dossier: the full decision record that caused this trade (I4).
    """

    trade_id: int
    symbol: str
    side: str
    qty: float
    requested_price: float
    fill_price: float
    fee: float
    notional: float
    position_after: float
    cash_after: float
    equity_after: float
    as_of: str = ""
    dossier: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "requested_price": self.requested_price,
            "fill_price": self.fill_price,
            "fee": self.fee,
            "notional": self.notional,
            "position_after": self.position_after,
            "cash_after": self.cash_after,
            "equity_after": self.equity_after,
            "as_of": self.as_of,
            "dossier": dict(self.dossier),
        }


class PaperBroker:
    """Simulated broker: instant fills with slippage + fees, no real capital.

    Satisfies the ``Broker`` protocol with ``is_paper = True`` — the flag the
    execution layer checks before accepting any order (I1).
    """

    is_paper: bool = True

    def __init__(
        self,
        cash: float = 100_000.0,
        fee_bps: float = 10.0,
        slippage_bps: float = 5.0,
        cost_model: CostModel | None = None,
    ) -> None:
        """
        Args:
            cash: starting (paper) cash.
            fee_bps: fee per fill, basis points of notional.
            slippage_bps: adverse fill slippage, basis points of price.
            cost_model: fill-pricing model (module 26); when omitted, a
                :class:`~quantos.execution.costs.FlatCostModel` built from
                ``fee_bps``/``slippage_bps`` reproduces the original flat
                behaviour bit-for-bit (back-compatible).
        """
        self.cash = float(cash)
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)
        self.cost_model: CostModel = (
            cost_model
            if cost_model is not None
            else FlatCostModel(fee_bps=float(fee_bps), slippage_bps=float(slippage_bps))
        )
        self.positions: dict[str, float] = {}
        self.trades: list[TradeRecord] = []

    def position(self, symbol: str) -> float:
        """Signed position held in ``symbol`` (0.0 when none)."""
        return self.positions.get(symbol, 0.0)

    def equity(self, prices: dict[str, float] | None = None) -> float:
        """Cash plus positions marked at ``prices`` (or their last fill price)."""
        total = self.cash
        for symbol, qty in self.positions.items():
            if prices and symbol in prices:
                mark = prices[symbol]
            else:
                mark = next(
                    (t.fill_price for t in reversed(self.trades) if t.symbol == symbol), 0.0
                )
            total += qty * mark
        return total

    def submit(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        as_of: str = "",
        dossier: dict[str, Any] | None = None,
        book: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> TradeRecord:
        """Fill a simulated order — priced by the cost model — and record it.

        Args:
            symbol: market to trade.
            side: ``"buy"`` or ``"sell"``.
            qty: positive quantity.
            price: reference price at decision time.
            as_of: decision bar timestamp (kept for reproducibility, I8).
            dossier: the full decision record behind this trade (I4).
            book: optional current liquidity context for the cost model
                (as-of the fill's bar only, I2).
            regime: optional active market regime for the cost model.

        Returns:
            The :class:`TradeRecord` of the fill.

        Raises:
            ValueError: on an invalid side, quantity or price.
        """
        fill = self.cost_model.fill(side, qty, price, book=book, regime=regime)
        fill_price = fill.fill_price
        notional = fill.notional
        fee = fill.fee

        if side == BUY:
            self.cash -= notional + fee
            self.positions[symbol] = self.position(symbol) + qty
        else:
            self.cash += notional - fee
            self.positions[symbol] = self.position(symbol) - qty

        record = TradeRecord(
            trade_id=len(self.trades) + 1,
            symbol=symbol,
            side=side,
            qty=qty,
            requested_price=price,
            fill_price=fill_price,
            fee=fee,
            notional=notional,
            position_after=self.positions[symbol],
            cash_after=self.cash,
            equity_after=self.equity({symbol: fill_price}),
            as_of=as_of,
            dossier=dict(dossier or {}),
        )
        self.trades.append(record)
        return record

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable account summary."""
        return {
            "is_paper": self.is_paper,
            "cash": self.cash,
            "positions": dict(self.positions),
            "n_trades": len(self.trades),
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
        }
