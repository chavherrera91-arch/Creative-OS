"""Storage abstraction: a tiered, upsertable table store.

Three tiers model the lake's flow of data:

* ``raw``      — data exactly as fetched from a connector.
* ``curated``  — validated, typed, deduplicated (primary-key unique).
* ``features`` — ML/research-ready derived tables.

The :class:`Store` Protocol is the single contract every backend implements
(DuckDB offline, Timescale in production). Callers depend on this, never on a
concrete backend (invariant I7).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

TIERS = ("raw", "curated", "features")


def validate_tier(tier: str) -> str:
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
    return tier


@runtime_checkable
class Store(Protocol):
    """A tiered table store with idempotent upserts."""

    def write(self, tier: str, table: str, df: pd.DataFrame) -> int:
        """Append ``df`` to ``tier.table``. Returns rows written."""
        ...

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        """Insert-or-replace ``df`` on ``keys``. Idempotent. Returns rows in table."""
        ...

    def read(
        self,
        tier: str,
        table: str,
        symbol: str | None = None,
        start=None,
        end=None,
    ) -> pd.DataFrame:
        """Read ``tier.table``, optionally filtered by symbol / time window."""
        ...

    def tables(self, tier: str) -> list[str]:
        """List table names present in ``tier``."""
        ...
