"""Tiered storage for the Data Lake (raw / curated / features)."""

from quantos.data.store.base import TIERS, Store
from quantos.data.store.duckdb_store import DuckDBStore


def get_store(root=None, **_kw) -> Store:
    """Return the default (offline) store. Timescale is opt-in and constructed
    explicitly by the caller when the ``[infra]`` extra is available."""
    return DuckDBStore(root=root)


__all__ = ["TIERS", "Store", "DuckDBStore", "get_store"]
