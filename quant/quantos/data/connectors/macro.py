"""Macro connector: dollar index, rates, risk appetite and event flags.

Deterministic synthetic series offline (I6); real feeds (FRED, an economic
calendar API...) plug in via ``_live_fetch`` with lazy imports and
env-provided keys only. The ``event_flag`` column drives the Risk Manager's
macro-event rule and (later) the regime engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.data.connectors._channel_base import ChannelConnector
from quantos.data.connectors._synthetic import cadence_index, canonical_periods, rng_for
from quantos.data.connectors.base import ConnectorMetadata, FetchRequest
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["MACRO_SCHEMA", "MacroConnector"]

_CADENCE = 21600  # 4 readings a day

MACRO_SCHEMA = Schema(
    name="macro",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime", description="point-in-time key (I2)"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("dxy", "float64", min=0.0, description="dollar index level"),
        FieldSpec("dxy_trend", "float64", description="signed dollar trend score"),
        FieldSpec("policy_rate", "float64", min=0.0, max=25.0, unit="%"),
        FieldSpec("rates_trend", "float64", description="signed rates trend score"),
        FieldSpec("risk_appetite", "float64", description="cross-asset risk appetite score"),
        FieldSpec("event_flag", "bool", description="a high-impact macro event is imminent"),
    ),
    primary_key=("symbol", "event_time"),
)
schema_registry.register(MACRO_SCHEMA)


@register
class MacroConnector(ChannelConnector):
    """Macro backdrop the Macro Analyst and Risk Manager read."""

    metadata = ConnectorMetadata(
        name="macro",
        category="macro",
        schema_name="macro",
        cadence_seconds=_CADENCE,
    )
    schema = MACRO_SCHEMA

    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        rng = rng_for(self.metadata.name, req.symbol, req.seed)
        index = cadence_index(_CADENCE, canonical_periods(_CADENCE))
        n = len(index)

        dxy = 104.0 + np.cumsum(rng.normal(0.0, 0.15, size=n))
        dxy_trend = np.clip(np.gradient(dxy) * 4.0, -1.5, 1.5)
        policy_rate = np.clip(5.25 + np.cumsum(rng.normal(0.0, 0.002, size=n)), 0.0, 25.0)
        rates_trend = np.clip(np.gradient(policy_rate) * 100.0, -1.5, 1.5)
        risk_appetite = np.clip(np.cumsum(rng.normal(0.0, 0.06, size=n)), -1.5, 1.5)
        # A deterministic calendar: one high-impact event window every ~2 weeks.
        event_flag = (np.arange(n) % 56) == 40

        return pd.DataFrame(
            {
                "symbol": req.symbol,
                "event_time": index,
                "ingested_at": index,
                "dxy": dxy,
                "dxy_trend": dxy_trend,
                "policy_rate": policy_rate,
                "rates_trend": rates_trend,
                "risk_appetite": risk_appetite,
                "event_flag": event_flag,
            }
        )
