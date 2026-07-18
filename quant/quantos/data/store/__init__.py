"""Tiered storage: ``raw`` → ``curated`` → ``features`` (M2).

The offline default is :class:`DuckDBStore` (Parquet on disk, or pure
in-memory frames); :class:`TimescaleStore` is the optional production backend
behind the ``[infra]`` extra. Both satisfy the :class:`Store` protocol.
"""

from quantos.data.store.base import TIERS, Store
from quantos.data.store.duckdb_store import DuckDBStore
from quantos.data.store.timescale_store import TimescaleStore

__all__ = ["TIERS", "DuckDBStore", "Store", "TimescaleStore"]
