"""Explainability engine (module 9).

Turns a :class:`CommitteeDecision` into a human narrative
(:func:`explain_decision`) and a JSON-serialisable report
(:func:`decision_report`). Nothing here re-analyses the market — it only
surfaces what the committee already recorded (invariant I4): the same evidence
that produced the decision produces the explanation.
"""

from __future__ import annotations

from typing import Any

from quantos.committee.base import Direction, Evidence
from quantos.committee.decision import CommitteeDecision

__all__ = ["decision_report", "explain_decision"]

_RULE = "=" * 66
_LINE = "-" * 66


def _verdict(decision: CommitteeDecision) -> str:
    if decision.approved:
        return f"{decision.direction.value} (approved)"
    if decision.blocked_by_risk:
        return "FLAT — BLOCKED BY RISK VETO"
    return "FLAT — STAND DOWN"


def _signed_evidence(decision: CommitteeDecision) -> tuple[list[Evidence], list[Evidence]]:
    """All non-abstention evidence split into bullish and bearish, strongest first."""
    pool = [e for opinion in decision.opinions if not opinion.abstained for e in opinion.evidence]
    bullish = sorted((e for e in pool if e.impact > 0), key=lambda e: -e.impact)
    bearish = sorted((e for e in pool if e.impact < 0), key=lambda e: e.impact)
    return bullish, bearish


def explain_decision(decision: CommitteeDecision) -> str:
    """Render the full narrative: Decision / Confidence / Reasons for &
    against / Risks / Analyst panel / Chair."""
    report = decision.confidence_report
    risk = decision.risk
    bullish, bearish = _signed_evidence(decision)
    lines: list[str] = [
        _RULE,
        "INVESTMENT COMMITTEE — DECISION REPORT",
        _RULE,
        f"Symbol     : {decision.symbol}  ({decision.timeframe} bars)",
        f"As of      : {decision.as_of}",
        f"Last price : {decision.price:,.2f}",
        f"DECISION   : {_verdict(decision)}",
    ]

    lines.append(_LINE)
    lines.append("CONFIDENCE")
    if report is not None:
        lines.append(
            f"  composite {report.confidence:.0%} "
            f"(threshold {report.threshold:.0%}) | "
            f"agreement {report.agreement:.0%} "
            f"(minimum {report.min_agreement:.0%}) | "
            f"{report.n_active} active / {len(report.abstentions)} abstained"
        )
    else:
        lines.append("  no confidence report attached")

    if decision.regime:
        lines.append(_LINE)
        lines.append("REGIME")
        label = decision.regime.get("label", "unknown")
        tradeable = decision.regime.get("tradeable", True)
        lines.append(f"  {label} (tradeable: {tradeable})")

    lines.append(_LINE)
    lines.append("REASONS FOR (bullish evidence)")
    if bullish:
        lines.extend(f"  [+{e.impact:.2f}] {e.name}: {e.detail}" for e in bullish[:6])
    else:
        lines.append("  none recorded")
    lines.append("REASONS AGAINST (bearish evidence)")
    if bearish:
        lines.extend(f"  [{e.impact:.2f}] {e.name}: {e.detail}" for e in bearish[:6])
    else:
        lines.append("  none recorded")

    lines.append(_LINE)
    lines.append("RISKS")
    if risk is not None:
        if risk.vetoes:
            lines.extend(f"  VETO    : {message}" for message in risk.vetoes)
        if risk.warnings:
            lines.extend(f"  warning : {message}" for message in risk.warnings)
        if not risk.vetoes and not risk.warnings:
            lines.append("  all risk checks passed")
    else:
        lines.append("  no risk assessment attached")

    lines.append(_LINE)
    lines.append("ANALYST PANEL")
    for opinion in decision.opinions:
        if opinion.abstained:
            reason = opinion.evidence[0].detail if opinion.evidence else "no reason recorded"
            lines.append(f"  {opinion.analyst:<22} ABSTAINED — {reason}")
        else:
            lines.append(
                f"  {opinion.analyst:<22} {opinion.direction.value:<5} "
                f"confidence {opinion.confidence:.0%} "
                f"({len(opinion.evidence)} pieces of evidence)"
            )

    lines.append(_LINE)
    lines.append("CHAIR")
    lines.extend(f"  {reason}" for reason in decision.reasons)
    lines.append(_RULE)
    return "\n".join(lines)


def decision_report(decision: CommitteeDecision) -> dict[str, Any]:
    """The JSON-serialisable companion of :func:`explain_decision` (I4).

    Returns:
        Dict with the complete decision record, the narrative, and the
        bullish/bearish evidence split used to build it.
    """
    bullish, bearish = _signed_evidence(decision)
    return {
        "decision": decision.as_dict(),
        "verdict": _verdict(decision),
        "narrative": explain_decision(decision),
        "reasons_for": [e.as_dict() for e in bullish],
        "reasons_against": [e.as_dict() for e in bearish],
        "abstentions": [o.analyst for o in decision.opinions if o.abstained],
        "vetoed": decision.blocked_by_risk,
        "stood_down": not decision.approved
        and not decision.blocked_by_risk
        and decision.direction is Direction.FLAT,
    }
