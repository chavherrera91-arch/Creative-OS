"""Risk engine: composable limit library (M3), meta-risk (M9).

Submodules are imported directly (``from quantos.risk.limits import ...``,
``from quantos.risk.meta import MetaRisk``) to avoid an import cycle: the
limit library sits underneath the committee/archive stack that Meta-Risk
reads back from.
"""
