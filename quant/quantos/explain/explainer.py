"""Render a :class:`CommitteeDecision` as an auditable, human-readable report.

Every decision must answer: what, how sure, why, and what are the risks. The
report groups the positive drivers and the risks separately, exactly so that when
a trade goes wrong you can point at the analyst and the evidence responsible.
"""

from __future__ import annotations

from quantos.committee.base import Direction, Evidence
from quantos.committee.decision import CommitteeDecision


def _fmt_evidence(items: list[Evidence]) -> list[str]:
    return [f"    - {e.name}: {e.detail} (impact {e.impact:+.2f})" for e in items]


def explain_decision(decision: CommitteeDecision) -> str:
    """Produce the Bloomberg-style narrative for a decision."""
    d = decision
    lines: list[str] = []
    verdict = "STAND DOWN" if d.direction is Direction.FLAT else str(d.direction)

    lines.append("=" * 64)
    lines.append(f" DECISION: {verdict}  {d.symbol} [{d.timeframe}]  @ {d.price:,.2f}")
    lines.append(f" {d.timestamp.isoformat()}")
    lines.append("=" * 64)
    lines.append(f" Proposed direction : {d.proposed_direction}")
    lines.append(f" Composite confidence: {d.confidence:.1%}")
    lines.append(f" Agreement          : {d.confidence_report.agreement:.1%}")
    lines.append(
        f" Participants        : {d.confidence_report.participants}"
        f" ({d.confidence_report.abstentions} abstained)"
    )
    lines.append(f" Approved           : {'YES' if d.approved else 'NO'}")
    if d.blocked_by_risk:
        lines.append(" Status             : BLOCKED BY RISK MANAGER")

    # Positive / negative drivers, pulled from analyst evidence.
    bullish: list[str] = []
    bearish: list[str] = []
    for op in d.opinions:
        if op.abstained:
            continue
        for e in op.evidence:
            tag = f"[{op.category}] {e.detail}"
            if e.impact > 0.01:
                bullish.append(f"    + {tag} ({e.impact:+.2f})")
            elif e.impact < -0.01:
                bearish.append(f"    - {tag} ({e.impact:+.2f})")

    lines.append("")
    lines.append(" REASONS FOR:")
    lines.extend(bullish or ["    (none)"])
    lines.append("")
    lines.append(" REASONS AGAINST:")
    lines.extend(bearish or ["    (none)"])

    lines.append("")
    lines.append(" RISKS:")
    if d.risk.vetoes:
        lines.extend(f"    ! VETO: {v}" for v in d.risk.vetoes)
    if d.risk.warnings:
        lines.extend(f"    ~ {w}" for w in d.risk.warnings)
    if not d.risk.vetoes and not d.risk.warnings:
        lines.append("    (none flagged)")

    lines.append("")
    lines.append(" ANALYST PANEL:")
    for op in d.opinions:
        status = "ABSTAIN" if op.abstained else f"{op.direction} @ {op.confidence:.0%}"
        lines.append(f"  * {op.analyst:22s} {status}")

    lines.append("")
    lines.append(" CHAIR:")
    lines.extend(f"    {r}" for r in d.reasons)
    lines.append("=" * 64)
    return "\n".join(lines)


def decision_report(decision: CommitteeDecision) -> dict:
    """Structured (JSON-serialisable) form of the decision, for logging / audit."""
    return decision.as_dict()
