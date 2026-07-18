"""Sentiment connector: blended social score + per-platform breakdown.

Deterministic synthetic series offline (I6); real feeds (Reddit, X,
Telegram APIs...) plug in via ``_live_fetch`` with lazy imports and
env-provided keys only. The blended ``score`` (validated to [-1, 1]) is the
value the Sentiment Analyst reads.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.data.connectors._channel_base import ChannelConnector
from quantos.data.connectors._synthetic import cadence_index, canonical_periods, rng_for
from quantos.data.connectors.base import ConnectorMetadata, FetchRequest
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["SENTIMENT_SCHEMA", "SentimentConnector"]

_CADENCE = 3600

SENTIMENT_SCHEMA = Schema(
    name="sentiment",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime", description="point-in-time key (I2)"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("score", "float64", min=-1.0, max=1.0, description="blended social score"),
        FieldSpec("volume", "float64", min=0.0, description="normalised message volume"),
        FieldSpec("reddit_score", "float64", min=-1.0, max=1.0),
        FieldSpec("x_score", "float64", min=-1.0, max=1.0),
        FieldSpec("telegram_score", "float64", min=-1.0, max=1.0),
    ),
    primary_key=("symbol", "event_time"),
)
schema_registry.register(SENTIMENT_SCHEMA)


@register
class SentimentConnector(ChannelConnector):
    """Crowd mood: an AR(1) blended score plus per-platform components."""

    metadata = ConnectorMetadata(
        name="sentiment",
        category="sentiment",
        schema_name="sentiment",
        cadence_seconds=_CADENCE,
    )
    schema = SENTIMENT_SCHEMA

    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        rng = rng_for(self.metadata.name, req.symbol, req.seed)
        index = cadence_index(_CADENCE, canonical_periods(_CADENCE))
        n = len(index)

        # Mean-reverting AR(1) so the score wanders but stays in range.
        shocks = rng.normal(0.0, 0.08, size=n)
        score = np.empty(n)
        score[0] = shocks[0]
        for i in range(1, n):
            score[i] = 0.97 * score[i - 1] + shocks[i]
        score = np.clip(score, -1.0, 1.0)

        def platform(noise_scale: float) -> np.ndarray:
            return np.clip(score + rng.normal(0.0, noise_scale, size=n), -1.0, 1.0)

        return pd.DataFrame(
            {
                "symbol": req.symbol,
                "event_time": index,
                "ingested_at": index,
                "score": score,
                "volume": rng.uniform(0.1, 1.0, size=n),
                "reddit_score": platform(0.15),
                "x_score": platform(0.12),
                "telegram_score": platform(0.2),
            }
        )
