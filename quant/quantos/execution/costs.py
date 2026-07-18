"""Execution realism: the cost model (module 26, M3 scope).

Replaces flat fee/slippage assumptions with a pluggable :class:`CostModel`
that prices every simulated fill: exchange fee + size-dependent slippage +
market impact, optionally liquidity- (order book) and regime-aware. Both the
:class:`~quantos.paper.broker.PaperBroker` and the backtest engine route
fills through it.

Back-compatibility is a hard requirement: :class:`FlatCostModel` reproduces
the M1 flat-bps behaviour bit-for-bit and :class:`ZeroCostModel` prices every
fill at the reference price with no fee. Every model is a pure, deterministic
function of its inputs — it sees only the current bar's price/book/regime,
never the future (I2, I8). These are *simulated* fills only; nothing here can
route a real order (I1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["CostModel", "Fill", "FlatCostModel", "ImpactCostModel", "ZeroCostModel"]

BUY = "buy"
SELL = "sell"


@dataclass(frozen=True)
class Fill:
    """One priced (simulated) fill.

    Attributes:
        side: ``"buy"`` or ``"sell"``.
        qty: quantity filled (positive; side carries the sign).
        price: reference price at decision time.
        fill_price: effective price after slippage + impact (always adverse).
        notional: ``qty * fill_price``.
        fee: exchange fee charged on the notional.
        slippage: adverse price displacement per unit from base slippage.
        impact: additional per-unit displacement from market impact (size).
        total_cost: fee plus all displacement costs, in cash terms — the
            all-in cost of this fill versus a free fill at ``price``.
    """

    side: str
    qty: float
    price: float
    fill_price: float
    notional: float
    fee: float
    slippage: float
    impact: float

    @property
    def total_cost(self) -> float:
        """All-in cash cost versus a free fill at the reference price."""
        return self.fee + (self.slippage + self.impact) * self.qty

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "side": self.side,
            "qty": self.qty,
            "price": self.price,
            "fill_price": self.fill_price,
            "notional": self.notional,
            "fee": self.fee,
            "slippage": self.slippage,
            "impact": self.impact,
            "total_cost": self.total_cost,
        }


@runtime_checkable
class CostModel(Protocol):
    """Prices a simulated fill: fee + slippage + impact (module 26)."""

    def fill(
        self,
        side: str,
        qty: float,
        price: float,
        book: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> Fill:
        """Price a fill of ``qty`` at reference ``price``.

        ``book`` may carry current liquidity (e.g. ``depth_notional``) and
        ``regime`` the active market regime — both strictly as-of the fill's
        bar (I2).
        """
        ...


def _validate(side: str, qty: float, price: float) -> None:
    if side not in (BUY, SELL):
        raise ValueError(f"side must be '{BUY}' or '{SELL}', got {side!r}")
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")


def _make_fill(
    side: str, qty: float, price: float, fee_bps: float, displacement_bps: float, impact_bps: float
) -> Fill:
    """Assemble a Fill from bps components; displacement is always adverse."""
    slippage = price * displacement_bps / 10_000.0
    impact = price * impact_bps / 10_000.0
    shift = slippage + impact
    fill_price = price + shift if side == BUY else price - shift
    notional = qty * fill_price
    return Fill(
        side=side,
        qty=qty,
        price=price,
        fill_price=fill_price,
        notional=notional,
        fee=notional * fee_bps / 10_000.0,
        slippage=slippage,
        impact=impact,
    )


@dataclass(frozen=True)
class ZeroCostModel:
    """Frictionless fills: no fee, no slippage, no impact.

    The degenerate baseline every realism test compares against — with it,
    the backtest and paper broker reproduce their gross (cost-free) numbers.
    """

    def fill(
        self,
        side: str,
        qty: float,
        price: float,
        book: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> Fill:
        """Fill exactly at the reference price."""
        _validate(side, qty, price)
        return _make_fill(side, qty, price, fee_bps=0.0, displacement_bps=0.0, impact_bps=0.0)


@dataclass(frozen=True)
class FlatCostModel:
    """The M1 flat model: fixed fee bps + fixed adverse slippage bps.

    Size-independent by design — it reproduces the original
    :class:`~quantos.paper.broker.PaperBroker` arithmetic bit-for-bit
    (back-compatibility anchor for module 26).
    """

    fee_bps: float = 10.0
    slippage_bps: float = 5.0

    def fill(
        self,
        side: str,
        qty: float,
        price: float,
        book: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> Fill:
        """Price a fill with flat, size-independent costs."""
        _validate(side, qty, price)
        return _make_fill(
            side, qty, price, fee_bps=self.fee_bps, displacement_bps=self.slippage_bps,
            impact_bps=0.0,
        )


@dataclass(frozen=True)
class ImpactCostModel:
    """Realistic fills: fee + size-dependent slippage + square-root impact.

    The adverse displacement grows with order size following the square-root
    market-impact law: ``impact_bps = impact_coeff_bps * sqrt(notional /
    depth)`` where ``depth`` is the available liquidity — taken from the
    order book context (``book["depth_notional"]``) when supplied, else the
    configured reference depth. Base slippage is scaled up in stressed
    regimes (``regime["label"]`` in :attr:`regime_multipliers`) and an
    optional latency penalty models the price drifting away during order
    transit.

    Attributes:
        fee_bps: exchange fee, basis points of notional.
        slippage_bps: base adverse slippage, basis points of price.
        impact_coeff_bps: impact at ``notional == depth``, basis points.
        ref_depth_notional: fallback liquidity when no book is supplied.
        latency_bps: optional flat latency/queue penalty, basis points.
        regime_multipliers: per-regime-label multipliers on slippage +
            latency (e.g. crisis fills are worse).
    """

    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    impact_coeff_bps: float = 25.0
    ref_depth_notional: float = 1_000_000.0
    latency_bps: float = 0.0
    regime_multipliers: dict[str, float] = field(
        default_factory=lambda: {"HIGH_VOL": 2.0, "CRISIS": 4.0, "MACRO_EVENT": 1.5}
    )

    def fill(
        self,
        side: str,
        qty: float,
        price: float,
        book: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> Fill:
        """Price a fill whose cost grows with size and market stress."""
        _validate(side, qty, price)
        depth = float((book or {}).get("depth_notional", self.ref_depth_notional))
        if depth <= 0:
            depth = self.ref_depth_notional
        multiplier = 1.0
        if regime:
            multiplier = float(self.regime_multipliers.get(str(regime.get("label", "")), 1.0))
        displacement_bps = (self.slippage_bps + self.latency_bps) * multiplier
        impact_bps = self.impact_coeff_bps * math.sqrt(qty * price / depth) * multiplier
        return _make_fill(
            side, qty, price, fee_bps=self.fee_bps, displacement_bps=displacement_bps,
            impact_bps=impact_bps,
        )
