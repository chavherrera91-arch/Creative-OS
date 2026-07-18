"""Derivatives connector: funding, open interest, long/short ratio, basis.

Deterministic synthetic series offline (I6); a real backend (e.g. exchange
derivatives endpoints via ccxt) can be added by overriding ``_live_fetch``
with lazy imports — keys come from the environment only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.data.connectors._channel_base import ChannelConnector
from quantos.data.connectors._synthetic import cadence_index, canonical_periods, rng_for
from quantos.data.connectors.base import ConnectorMetadata, FetchRequest
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["DERIVATIVES_SCHEMA", "DerivativesConnector"]

_CADENCE = 3600

DERIVATIVES_SCHEMA = Schema(
    name="derivatives",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime", description="point-in-time key (I2)"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("funding_rate", "float64", min=-0.05, max=0.05, unit="rate/8h"),
        FieldSpec("open_interest", "float64", min=0.0, unit="contracts"),
        FieldSpec("oi_change", "float64", description="fractional OI change per interval"),
        FieldSpec("long_short_ratio", "float64", min=0.0),
        FieldSpec("basis_bps", "float64", unit="bps", description="perp-vs-spot basis"),
    ),
    primary_key=("symbol", "event_time"),
)
schema_registry.register(DERIVATIVES_SCHEMA)


@register
class DerivativesConnector(ChannelConnector):
    """Funding / OI / positioning for perpetual futures."""

    metadata = ConnectorMetadata(
        name="derivatives",
        category="derivatives",
        schema_name="derivatives",
        cadence_seconds=_CADENCE,
    )
    schema = DERIVATIVES_SCHEMA

    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        rng = rng_for(self.metadata.name, req.symbol, req.seed)
        index = cadence_index(_CADENCE, canonical_periods(_CADENCE))
        n = len(index)

        funding = np.clip(
            0.0001 + np.cumsum(rng.normal(0.0, 2e-5, size=n)), -0.05, 0.05
        )
        oi = 1e9 * np.exp(np.cumsum(rng.normal(0.0, 0.004, size=n)))
        oi_change = np.concatenate([[0.0], np.diff(oi) / oi[:-1]])
        ls_ratio = np.clip(1.0 + np.cumsum(rng.normal(0.0, 0.01, size=n)), 0.3, 3.0)
        basis = 5.0 + np.cumsum(rng.normal(0.0, 0.4, size=n))

        return pd.DataFrame(
            {
                "symbol": req.symbol,
                "event_time": index,
                "ingested_at": index,
                "funding_rate": funding,
                "open_interest": oi,
                "oi_change": oi_change,
                "long_short_ratio": ls_ratio,
                "basis_bps": basis,
            }
        )
