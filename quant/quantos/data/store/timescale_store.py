"""Production store: TimescaleDB (optional).

This module MUST import without a database driver present — ``psycopg`` is
imported lazily inside methods, never at module load. Constructing a
:class:`TimescaleStore` is what pulls the driver in. No DSN or secret is ever
hardcoded; the connection string comes from the caller / environment.

Install with the ``[infra]`` extra. In research/offline mode use
:class:`~quantos.data.store.duckdb_store.DuckDBStore` instead.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.store.base import validate_tier

_TIME_COL = "event_time"


class TimescaleStore:
    """Tiered store backed by TimescaleDB hypertables (lazy psycopg)."""

    is_persistent = True

    def __init__(self, dsn: str, schema: str = "quantos") -> None:
        if not dsn:
            raise ValueError("TimescaleStore requires a DSN (never hardcode secrets)")
        self.dsn = dsn
        self.schema = schema

    def _connect(self):
        try:
            import psycopg  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "TimescaleStore needs psycopg — install the '[infra]' extra, "
                "or use DuckDBStore for offline research."
            ) from exc
        return psycopg.connect(self.dsn)

    def _qualified(self, tier: str, table: str) -> str:
        validate_tier(tier)
        return f"{self.schema}.{tier}__{table}"

    def ensure_hypertable(self, tier: str, table: str, time_column: str = _TIME_COL) -> None:  # pragma: no cover - requires DB
        """Create the table (if absent) and promote it to a hypertable."""
        name = self._qualified(tier, table)
        with self._connect() as con, con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {name} "
                f"(symbol TEXT, {time_column} TIMESTAMPTZ, ingested_at TIMESTAMPTZ, "
                f"payload JSONB)"
            )
            cur.execute(
                f"SELECT create_hypertable('{name}', '{time_column}', "
                f"if_not_exists => TRUE)"
            )
            con.commit()

    def write(self, tier: str, table: str, df: pd.DataFrame) -> int:  # pragma: no cover - requires DB
        raise NotImplementedError(
            "TimescaleStore.write is a production stub; wire it when the '[infra]' "
            "extra and a live database are available."
        )

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:  # pragma: no cover - requires DB
        raise NotImplementedError("TimescaleStore.upsert is a production stub.")

    def read(self, tier: str, table: str, symbol=None, start=None, end=None) -> pd.DataFrame:  # pragma: no cover - requires DB
        raise NotImplementedError("TimescaleStore.read is a production stub.")

    def tables(self, tier: str) -> list[str]:  # pragma: no cover - requires DB
        raise NotImplementedError("TimescaleStore.tables is a production stub.")
