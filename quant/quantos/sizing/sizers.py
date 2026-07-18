"""Concrete position sizers (module 26, M3 scope).

Three classic capital-allocation policies behind the
:class:`~quantos.sizing.base.PositionSizer` port:

- :class:`VolTargetSizer` — lever the position so the asset contributes a
  target volatility; size falls as volatility rises.
- :class:`FractionalKellySizer` — a conservative fraction of the Kelly
  criterion, mapping the committee's confidence to the bet's edge.
- :class:`RiskParitySizer` — equalise the risk contribution of a fixed risk
  budget, discounted by correlation with the existing book.

Every sizer honours the shared hard rules (see ``sizing.base``): a vetoed or
unapproved decision sizes to 0.0, and the returned fraction can never exceed
the configured maximum-position limit — including a
:class:`~quantos.risk.limits.MaxPositionSize` risk limit when one is wired in
(invariant I5). All sizers are pure deterministic functions (I8).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quantos.committee.decision import CommitteeDecision
from quantos.risk.limits import MaxPositionSize

__all__ = ["FractionalKellySizer", "RiskParitySizer", "VolTargetSizer"]


class _BoundedSizer:
    """Shared bounding logic: the size can never breach the risk limit (I5)."""

    def __init__(self, max_fraction: float, limit: MaxPositionSize | None) -> None:
        """
        Args:
            max_fraction: the sizer's own cap on |size| (fraction of equity).
            limit: the Risk Manager's max-position limit; when supplied the
                effective cap is the *tighter* of the two — a sizer may never
                out-vote a risk limit (I5).
        """
        if max_fraction <= 0:
            raise ValueError(f"max_fraction must be positive, got {max_fraction}")
        self.max_fraction = max_fraction
        self.limit = limit

    @property
    def bound(self) -> float:
        """The effective cap on |size|."""
        if self.limit is not None:
            return min(self.max_fraction, self.limit.max_fraction)
        return self.max_fraction

    def _bounded(self, decision: CommitteeDecision, raw_fraction: float) -> float:
        """Sign by the decision's direction and clip into [-bound, bound]."""
        if not decision.approved or decision.blocked_by_risk:
            return 0.0  # a sizer never revives a veto or a stand-down (I5)
        sign = float(decision.direction.sign)
        if sign == 0.0:
            return 0.0
        return sign * min(max(raw_fraction, 0.0), self.bound)

    @staticmethod
    def _mean_corr(corr: Mapping[str, float] | float | None) -> float:
        """Average positive correlation with the book (0.0 when unknown)."""
        if corr is None:
            return 0.0
        if isinstance(corr, Mapping):
            values = [float(v) for v in corr.values()]
            if not values:
                return 0.0
            mean = sum(values) / len(values)
        else:
            mean = float(corr)
        return min(max(mean, 0.0), 0.95)


class VolTargetSizer(_BoundedSizer):
    """Size to a target volatility contribution: less size when vol is high."""

    def __init__(
        self,
        target_vol: float = 0.20,
        max_fraction: float = 0.25,
        limit: MaxPositionSize | None = None,
    ) -> None:
        """
        Args:
            target_vol: annualised volatility the position should contribute.
            max_fraction: the sizer's own cap on |size|.
            limit: optional Risk Manager max-position limit (I5).
        """
        super().__init__(max_fraction, limit)
        if target_vol <= 0:
            raise ValueError(f"target_vol must be positive, got {target_vol}")
        self.target_vol = target_vol

    def size(
        self,
        decision: CommitteeDecision,
        portfolio: dict[str, Any] | None = None,
        vol: float | None = None,
        corr: Mapping[str, float] | float | None = None,
    ) -> float:
        """``(target_vol / vol) * confidence``, bounded.

        Without a volatility estimate the sizer falls back to the
        confidence-scaled cap (it cannot target what it cannot measure).
        """
        if vol is None or vol <= 0.0:
            return self._bounded(decision, self.bound * decision.confidence)
        leverage = self.target_vol / vol
        return self._bounded(decision, leverage * decision.confidence)


class FractionalKellySizer(_BoundedSizer):
    """A conservative fraction of the Kelly criterion.

    The committee's confidence ``c`` is read as the win probability of a
    symmetric even-payout bet, ``p = 0.5 + c/2``, whose full-Kelly stake is
    ``f* = 2p - 1 = c``. Betting a *fraction* of Kelly trades a little growth
    for a large cut in variance and drawdown.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.5,
        max_fraction: float = 0.25,
        limit: MaxPositionSize | None = None,
    ) -> None:
        """
        Args:
            kelly_fraction: fraction of the full-Kelly stake to bet (0..1].
            max_fraction: the sizer's own cap on |size|.
            limit: optional Risk Manager max-position limit (I5).
        """
        super().__init__(max_fraction, limit)
        if not 0.0 < kelly_fraction <= 1.0:
            raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")
        self.kelly_fraction = kelly_fraction

    def size(
        self,
        decision: CommitteeDecision,
        portfolio: dict[str, Any] | None = None,
        vol: float | None = None,
        corr: Mapping[str, float] | float | None = None,
    ) -> float:
        """``kelly_fraction * confidence``, bounded."""
        return self._bounded(decision, self.kelly_fraction * decision.confidence)


class RiskParitySizer(_BoundedSizer):
    """Equalise risk contributions: a fixed risk budget divided by volatility.

    The raw stake ``risk_budget / vol`` is discounted by the asset's average
    positive correlation with the existing book — a highly-correlated
    position adds less diversification and gets less capital.
    """

    def __init__(
        self,
        risk_budget: float = 0.05,
        max_fraction: float = 0.25,
        limit: MaxPositionSize | None = None,
    ) -> None:
        """
        Args:
            risk_budget: annualised volatility budget this position may spend.
            max_fraction: the sizer's own cap on |size|.
            limit: optional Risk Manager max-position limit (I5).
        """
        super().__init__(max_fraction, limit)
        if risk_budget <= 0:
            raise ValueError(f"risk_budget must be positive, got {risk_budget}")
        self.risk_budget = risk_budget

    def size(
        self,
        decision: CommitteeDecision,
        portfolio: dict[str, Any] | None = None,
        vol: float | None = None,
        corr: Mapping[str, float] | float | None = None,
    ) -> float:
        """``(risk_budget / vol) * (1 - mean positive corr)``, bounded.

        Without a volatility estimate the sizer falls back to the
        confidence-scaled cap, still correlation-discounted.
        """
        penalty = 1.0 - self._mean_corr(corr)
        if vol is None or vol <= 0.0:
            return self._bounded(decision, self.bound * decision.confidence * penalty)
        return self._bounded(decision, (self.risk_budget / vol) * penalty)
