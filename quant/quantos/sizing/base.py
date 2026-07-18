"""The position-sizing port (module 26, M3 scope).

A :class:`PositionSizer` turns a :class:`~quantos.committee.decision.
CommitteeDecision` (direction + confidence) into a **signed position size as a
fraction of equity**, informed by volatility and correlation. Two rules are
absolute:

- a sizer never revives a vetoed or unapproved decision — those size to 0.0
  (invariant I5);
- a sizer never exceeds the Risk Manager's maximum-position limit — sizes are
  clipped against it, and the executor clamps again as defence in depth (I5).

Sizing only ever feeds the **paper** execution engine (I1) and is a pure,
deterministic function of its inputs (I8).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from quantos.committee.decision import CommitteeDecision

__all__ = ["PositionSizer"]


@runtime_checkable
class PositionSizer(Protocol):
    """Turns a committee decision into a bounded position size."""

    def size(
        self,
        decision: CommitteeDecision,
        portfolio: dict[str, Any] | None = None,
        vol: float | None = None,
        corr: Mapping[str, float] | float | None = None,
    ) -> float:
        """Signed target position as a fraction of equity.

        Args:
            decision: the committee's call; unapproved/vetoed decisions must
                size to 0.0 (I5).
            portfolio: current book context (equity, open positions, ...).
            vol: annualised volatility of the asset, when known.
            corr: correlation(s) of the asset with the existing book — a
                single float or a mapping per held symbol.

        Returns:
            A signed fraction of equity, never exceeding the configured
            maximum-position limit in absolute value (I5).
        """
        ...
