"""quantos — AI Quant Research Platform.

Research-first, multi-agent quantitative research platform. The centrepiece is
the :class:`~quantos.committee.committee.InvestmentCommittee`: a panel of
specialist analysts whose evidence is aggregated into a confidence score, with a
Risk Manager that can *veto* any trade. Nothing here touches real capital — live
execution is hard-disabled (see :mod:`quantos.execution.interfaces`).
"""

from __future__ import annotations

__version__ = "0.1.0"

from quantos.committee.base import Direction

__all__ = ["Direction", "__version__"]
