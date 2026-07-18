"""News connector: tagged headlines with a deterministic keyword tagger.

In M2 the tagger is a deterministic keyword stub so the connector is fully
offline-testable (I6); the M6 LLM tagger swaps in behind the same schema
with no downstream change. Real feeds (RSS, news APIs) plug in via
``_live_fetch`` with lazy imports and env-provided keys only.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.connectors._channel_base import ChannelConnector
from quantos.data.connectors._synthetic import cadence_index, canonical_periods, rng_for
from quantos.data.connectors.base import ConnectorMetadata, FetchRequest
from quantos.data.connectors.registry import register
from quantos.data.schema import FieldSpec, Schema, schema_registry

__all__ = ["NEWS_SCHEMA", "NewsConnector", "tag_headline"]

_CADENCE = 21600  # a headline batch every 6 hours

NEWS_SCHEMA = Schema(
    name="news",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime", description="publication time (I2)"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("news_id", "string", description="natural id (stable per headline)"),
        FieldSpec("source", "string"),
        FieldSpec("headline", "string"),
        FieldSpec("tag", "string", description="topic tag from the keyword stub (LLM in M6)"),
        FieldSpec("sentiment", "float64", min=-1.0, max=1.0),
    ),
    primary_key=("symbol", "event_time", "news_id"),
)
schema_registry.register(NEWS_SCHEMA)

#: Deterministic keyword → (tag, sentiment) rules. First match wins.
_TAG_RULES: tuple[tuple[str, str, float], ...] = (
    ("etf", "regulation", 0.6),
    ("approval", "regulation", 0.5),
    ("ban", "regulation", -0.7),
    ("lawsuit", "regulation", -0.5),
    ("hack", "security", -0.8),
    ("exploit", "security", -0.7),
    ("upgrade", "technology", 0.4),
    ("adoption", "adoption", 0.6),
    ("institutional", "adoption", 0.5),
    ("fed", "macro", -0.2),
    ("rate", "macro", -0.2),
    ("liquidation", "market", -0.5),
    ("rally", "market", 0.5),
    ("all-time high", "market", 0.7),
)

_HEADLINE_TEMPLATES: tuple[str, ...] = (
    "Spot ETF inflows accelerate as institutional adoption grows",
    "Exchange reports security incident, hack under investigation",
    "Regulators weigh approval of new listed products",
    "Fed signals higher-for-longer rate path",
    "Network upgrade ships on schedule, fees drop",
    "Large liquidation cascade hits derivatives markets",
    "Broad crypto rally lifts majors to new range highs",
    "Lawsuit filed against major market maker",
    "Stablecoin issuer expands reserves, supply grows",
    "Mining difficulty reaches record as hashrate climbs",
)

_SOURCES: tuple[str, ...] = ("wire", "desk", "chain-weekly", "macro-brief")


def tag_headline(headline: str) -> tuple[str, float]:
    """Deterministic keyword tagger: headline → (topic tag, sentiment).

    A rule-based stand-in for the M6 LLM tagger; same output schema, so the
    swap is invisible downstream.
    """
    lowered = headline.lower()
    for keyword, tag, sentiment in _TAG_RULES:
        if keyword in lowered:
            return tag, sentiment
    return "general", 0.0


@register
class NewsConnector(ChannelConnector):
    """Tagged headlines with deterministic offline generation."""

    metadata = ConnectorMetadata(
        name="news",
        category="news",
        schema_name="news",
        cadence_seconds=_CADENCE,
    )
    schema = NEWS_SCHEMA

    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        rng = rng_for(self.metadata.name, req.symbol, req.seed)
        index = cadence_index(_CADENCE, canonical_periods(_CADENCE))
        n = len(index)

        picks = rng.integers(0, len(_HEADLINE_TEMPLATES), size=n)
        sources = rng.integers(0, len(_SOURCES), size=n)
        headlines = [_HEADLINE_TEMPLATES[i] for i in picks]
        tagged = [tag_headline(h) for h in headlines]

        return pd.DataFrame(
            {
                "symbol": req.symbol,
                "event_time": index,
                "ingested_at": index,
                "news_id": [f"news-{k}-{picks[k]}" for k in range(n)],
                "source": [_SOURCES[s] for s in sources],
                "headline": headlines,
                "tag": [t for t, _ in tagged],
                "sentiment": [s for _, s in tagged],
            }
        )
