"""Optional TimescaleDB store (production hot tier, ``[infra]`` extra).

The module imports with **no database driver installed** (invariant I6):
``psycopg`` is imported lazily inside the connection helper, the DSN comes
only from an argument or the ``QUANTOS_TIMESCALE_DSN`` environment variable
(never hardcoded), and every method degrades to a clear ``RuntimeError``
when the driver or database is unavailable. The offline default backend is
:class:`~quantos.data.store.duckdb_store.DuckDBStore`.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

import pandas as pd

from quantos.data.schema.base import Schema
from quantos.data.store.base import check_tier

__all__ = ["TimescaleStore"]

_DSN_ENV = "QUANTOS_TIMESCALE_DSN"

_DTYPE_SQL: dict[str, str] = {
    "float64": "DOUBLE PRECISION",
    "int64": "BIGINT",
    "string": "TEXT",
    "bool": "BOOLEAN",
    "datetime": "TIMESTAMPTZ",
}


class TimescaleStore:
    """Timescale-backed tiered store; satisfies the ``Store`` protocol.

    Tables live as ``<tier>_<table>`` hypertables partitioned on
    ``event_time``. Purely optional: research and tests never require it.
    """

    def __init__(self, dsn: str | None = None) -> None:
        """
        Args:
            dsn: PostgreSQL/Timescale DSN. Falls back to the
                ``QUANTOS_TIMESCALE_DSN`` environment variable; no default is
                ever hardcoded (no secrets in code).
        """
        self.dsn = dsn or os.environ.get(_DSN_ENV)

    # -- plumbing ------------------------------------------------------------

    def _connect(self) -> Any:
        """Lazily import psycopg and open a connection.

        Raises:
            RuntimeError: when psycopg is not installed or no DSN is set —
                a clear, actionable message instead of an ImportError at
                module import time (I6).
        """
        try:
            import psycopg  # noqa: PLC0415 — optional extra, lazy on purpose (I6)
        except ImportError as exc:
            raise RuntimeError(
                "TimescaleStore needs the optional 'psycopg' package "
                "(pip install 'quantos[infra]'); the offline default is DuckDBStore"
            ) from exc
        if not self.dsn:
            raise RuntimeError(
                f"TimescaleStore has no DSN: pass one or set {_DSN_ENV} (never hardcoded)"
            )
        return psycopg.connect(self.dsn)

    @staticmethod
    def _table_name(tier: str, table: str) -> str:
        check_tier(tier)
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in table)
        return f"{tier}_{safe}"

    def _ensure_table(self, conn: Any, name: str, df: pd.DataFrame, schema: Schema | None) -> None:
        """Create the table (and hypertable) on first write."""
        if schema is not None:
            columns = ", ".join(
                f'"{f.name}" {_DTYPE_SQL.get(f.dtype, "TEXT")}'
                + ("" if f.nullable else " NOT NULL")
                for f in schema.fields
            )
            pk = ", ".join(f'"{k}"' for k in schema.primary_key)
            ddl = f"CREATE TABLE IF NOT EXISTS {name} ({columns}, PRIMARY KEY ({pk}))"
        else:
            columns = ", ".join(f'"{c}" TEXT' for c in df.columns)
            ddl = f"CREATE TABLE IF NOT EXISTS {name} ({columns})"
        conn.execute(ddl)
        self.ensure_hypertable(conn, name, (schema.time_column if schema else "event_time"))

    @staticmethod
    def ensure_hypertable(conn: Any, name: str, time_column: str = "event_time") -> None:
        """Best-effort conversion into a Timescale hypertable."""
        with contextlib.suppress(Exception):  # plain Postgres (no timescale ext) is fine
            conn.execute(
                "SELECT create_hypertable(%s, %s, if_not_exists => TRUE)", (name, time_column)
            )

    # -- Store protocol -------------------------------------------------------

    def write(self, tier: str, table: str, df: pd.DataFrame, schema: Schema | None = None) -> int:
        """Append rows; returns rows written."""
        if df.empty:
            return 0
        name = self._table_name(tier, table)
        with self._connect() as conn:
            self._ensure_table(conn, name, df, schema)
            cols = ", ".join(f'"{c}"' for c in df.columns)
            slots = ", ".join(["%s"] * len(df.columns))
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {name} ({cols}) VALUES ({slots})",
                    [tuple(row) for row in df.itertuples(index=False)],
                )
        return len(df)

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        """Insert-or-replace on ``keys`` (``ON CONFLICT DO UPDATE``); idempotent."""
        if df.empty:
            return 0
        name = self._table_name(tier, table)
        with self._connect() as conn:
            self._ensure_table(conn, name, df, None)
            cols = ", ".join(f'"{c}"' for c in df.columns)
            slots = ", ".join(["%s"] * len(df.columns))
            conflict = ", ".join(f'"{k}"' for k in keys)
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in df.columns if c not in keys)
            sql = (
                f"INSERT INTO {name} ({cols}) VALUES ({slots}) "
                f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
            )
            with conn.cursor() as cur:
                cur.executemany(sql, [tuple(row) for row in df.itertuples(index=False)])
        return len(df)

    def read(
        self,
        tier: str,
        table: str,
        symbol: str | None = None,
        start: Any | None = None,
        end: Any | None = None,
    ) -> pd.DataFrame:
        """Read a table filtered by symbol and event-time window."""
        name = self._table_name(tier, table)
        clauses, params = [], []
        if symbol is not None:
            clauses.append("symbol = %s")
            params.append(symbol)
        if start is not None:
            clauses.append("event_time >= %s")
            params.append(pd.Timestamp(start))
        if end is not None:
            clauses.append("event_time <= %s")
            params.append(pd.Timestamp(end))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {name}{where} ORDER BY event_time", params)
            columns = [d.name for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)

    def tables(self, tier: str) -> list[str]:
        """List tables in a tier (by the ``<tier>_`` naming convention)."""
        check_tier(tier)
        prefix = f"{tier}_"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename LIKE %s",
                (prefix + "%",),
            )
            return sorted(row[0][len(prefix) :] for row in cur.fetchall())
