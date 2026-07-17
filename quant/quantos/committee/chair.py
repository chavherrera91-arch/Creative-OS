"""The Chair — the committee's president (ARCHITECTURE §3).

Applies the decision hierarchy, strictly in order:

1. **Regime gate** — an untradeable regime (context ``regime`` with
   ``tradeable: False``) stands the committee down before anything else.
2. **Risk veto** — any Risk Manager veto forces FLAT regardless of confidence
   (invariant I5, absolute).
3. **Evidence threshold** — trade only when composite confidence *and*
   agreement clear their bars.
4. Otherwise **stand down** — a valid, logged outcome, not a failure.
"""

from __future__ import annotations

from typing import Any

from quantos.committee.base import AnalystOpinion, Direction
from quantos.committee.confidence import ConfidenceReport
from quantos.committee.decision import CommitteeDecision
from quantos.committee.risk_manager import RiskAssessment
from quantos.data.models import MarketSnapshot

__all__ = ["Chair"]


class Chair:
    """Synthesises analysts, confidence and risk into the final call."""

    def __init__(self, name: str = "Chair") -> None:
        self.name = name

    def decide(
        self,
        snapshot: MarketSnapshot,
        opinions: list[AnalystOpinion],
        report: ConfidenceReport,
        risk: RiskAssessment,
        context: dict[str, Any] | None = None,
        run_manifest: dict[str, Any] | None = None,
    ) -> CommitteeDecision:
        """Render the final :class:`CommitteeDecision` via the hierarchy above."""
        context = context or {}
        regime: dict[str, Any] = dict(context.get("regime") or {})
        strategies: list[dict[str, Any]] = list(context.get("strategies_considered") or [])
        reasons: list[str] = []

        direction = Direction.FLAT
        approved = False
        blocked_by_risk = False

        # 1. Regime gate — before anything else.
        if regime and regime.get("tradeable") is False:
            label = regime.get("label", "unknown")
            reasons.append(f"regime gate: '{label}' is untradeable — standing down")

        # 2. Risk veto — absolute (I5).
        elif risk.vetoed:
            blocked_by_risk = True
            reasons.append("risk veto (absolute, I5): the Risk Manager blocked this trade")
            reasons.extend(f"veto: {message}" for message in risk.vetoes)
            if report.direction is not Direction.FLAT:
                reasons.append(
                    f"overridden conviction: committee leaned {report.direction.value} "
                    f"at {report.confidence:.0%} confidence"
                )

        # 3. Evidence threshold.
        elif report.meets_threshold:
            direction = report.direction
            approved = True
            reasons.append(
                f"evidence cleared the bar: {report.direction.value} at "
                f"{report.confidence:.0%} confidence "
                f"(threshold {report.threshold:.0%}), agreement {report.agreement:.0%} "
                f"(minimum {report.min_agreement:.0%})"
            )
            reasons.extend(f"warning noted: {message}" for message in risk.warnings)

        # 4. Stand down — insufficient evidence.
        else:
            if report.n_active == 0:
                reasons.append("standing down: every analyst abstained (no data, I3)")
            else:
                reasons.append(
                    f"standing down: insufficient evidence — confidence "
                    f"{report.confidence:.0%} (threshold {report.threshold:.0%}), "
                    f"agreement {report.agreement:.0%} "
                    f"(minimum {report.min_agreement:.0%}), "
                    f"composite direction {report.direction.value}"
                )

        return CommitteeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            price=snapshot.last_price,
            direction=direction,
            approved=approved,
            confidence=report.confidence,
            blocked_by_risk=blocked_by_risk,
            reasons=reasons,
            opinions=opinions,
            confidence_report=report,
            risk=risk,
            regime=regime,
            strategies_considered=strategies,
            run_manifest=dict(run_manifest or {}),
            as_of=snapshot.as_of,
        )
