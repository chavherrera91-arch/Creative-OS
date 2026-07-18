"""Per-(connector, symbol) watermarks — ingestion is resumable (§1.4).

A watermark records the highest ``event_time`` successfully ingested for one
connector/symbol pair. Re-running ingestion resumes from it (no duplicate
fetching), and a crash loses nothing: the next run picks up where the last
completed write left off. Persisted through the ``Store`` so it survives
restarts alongside the data itself.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.store.base import Store

__all__ = ["WatermarkStore"]

_TIER = "raw"  # operational metadata lives beside the raw tier
_TABLE = "_watermarks"


class WatermarkStore:
    """Load/advance watermarks, persisted via any ``Store`` backend."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def get(self, connector: str, symbol: str) -> pd.Timestamp | None:
        """The last ingested ``event_time`` for a connector/symbol, if any."""
        table = self.store.read(_TIER, _TABLE)
        if table.empty:
            return None
        match = table[(table["connector"] == connector) & (table["symbol"] == symbol)]
        if match.empty:
            return None
        return pd.Timestamp(match["watermark"].iloc[-1])

    def set(self, connector: str, symbol: str, watermark: pd.Timestamp) -> None:
        """Advance (or create) a watermark; idempotent on the pair key."""
        row = pd.DataFrame(
            {
                "connector": [connector],
                "symbol": [symbol],
                "watermark": [pd.Timestamp(watermark)],
            }
        )
        self.store.upsert(_TIER, _TABLE, row, keys=["connector", "symbol"])

    def all(self) -> pd.DataFrame:
        """Every stored watermark (connector, symbol, watermark)."""
        return self.store.read(_TIER, _TABLE)
