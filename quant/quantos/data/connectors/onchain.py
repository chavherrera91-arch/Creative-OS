"""On-chain connector: exchange flows, whale accumulation, stablecoin supply.

Deterministic synthetic series offline (I6); a real backend (Glassnode,
Dune, node RPC...) plugs in via ``_live_fetch`` with lazy imports and
env-provided keys only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.data.connectors._channel_base import ChannelConnector
from quantos.data.connectors._synthetic import cadence_index, canonical_periods, rng_for
from quantos.data.connectors.base import ConnectorMetadata, FetchRequest
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["ONCHAIN_SCHEMA", "OnChainConnector"]

_CADENCE = 3600

ONCHAIN_SCHEMA = Schema(
    name="onchain",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime", description="point-in-time key (I2)"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("inflow", "float64", min=0.0, unit="coins"),
        FieldSpec("outflow", "float64", min=0.0, unit="coins"),
        FieldSpec("net_exchange_flow", "float64", unit="coins", description="inflow - outflow"),
        FieldSpec("whale_accumulation", "float64", description="signed accumulation score"),
        FieldSpec("stablecoin_supply", "float64", min=0.0, unit="USD"),
        FieldSpec("stablecoin_supply_change", "float64", description="fractional change"),
    ),
    primary_key=("symbol", "event_time"),
)
schema_registry.register(ONCHAIN_SCHEMA)


@register
class OnChainConnector(ChannelConnector):
    """Exchange flows, whales and stablecoin dry powder."""

    metadata = ConnectorMetadata(
        name="onchain",
        category="onchain",
        schema_name="onchain",
        cadence_seconds=_CADENCE,
    )
    schema = ONCHAIN_SCHEMA

    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        rng = rng_for(self.metadata.name, req.symbol, req.seed)
        index = cadence_index(_CADENCE, canonical_periods(_CADENCE))
        n = len(index)

        inflow = rng.lognormal(mean=6.5, sigma=0.35, size=n)
        outflow = rng.lognormal(mean=6.5, sigma=0.35, size=n)
        whale = np.clip(np.cumsum(rng.normal(0.0, 0.05, size=n)), -2.0, 2.0)
        supply = 1.3e11 * np.exp(np.cumsum(rng.normal(0.0, 0.0008, size=n)))
        supply_change = np.concatenate([[0.0], np.diff(supply) / supply[:-1]])

        return pd.DataFrame(
            {
                "symbol": req.symbol,
                "event_time": index,
                "ingested_at": index,
                "inflow": inflow,
                "outflow": outflow,
                "net_exchange_flow": inflow - outflow,
                "whale_accumulation": whale,
                "stablecoin_supply": supply,
                "stablecoin_supply_change": supply_change,
            }
        )
