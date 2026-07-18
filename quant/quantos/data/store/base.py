"""The tiered :class:`Store` port (DATA_INFRASTRUCTURE §3.5).

Three tiers: ``raw`` (as fetched), ``curated`` (validated, typed, deduped on
primary key) and ``features`` (research/ML-ready). Any backend that satisfies
the protocol plugs into the ingestion runner and the lake without core edits
(invariant I7).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd

from quantos.data.schema.base import Schema

__all__ = ["TIERS", "Store", "check_tier"]

#: The legal storage tiers, in lineage order.
TIERS: tuple[str, ...] = ("raw", "curated", "features")


def check_tier(tier: str) -> str:
    """Validate a tier name, returning it unchanged.

    Raises:
        ValueError: for anything outside :data:`TIERS`.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
    return tier


@runtime_checkable
class Store(Protocol):
    """Tiered persistence port — implementations must be idempotent on upsert."""

    def write(self, tier: str, table: str, df: pd.DataFrame, schema: Schema | None = None) -> int:
        """Append rows to a table; returns the number of rows written."""
        ...

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        """Insert-or-replace on ``keys`` (idempotent); returns net-new rows."""
        ...

    def read(
        self,
        tier: str,
        table: str,
        symbol: str | None = None,
        start: Any | None = None,
        end: Any | None = None,
    ) -> pd.DataFrame:
        """Read a table, optionally filtered by symbol and event-time window."""
        ...

    def tables(self, tier: str) -> list[str]:
        """List the tables present in a tier."""
        ...
