"""Offline-first tiered store: Parquet on disk, DuckDB for ad-hoc SQL.

``DuckDBStore`` is the default backend (invariant I6):

- with no ``root`` it keeps every table as an in-memory DataFrame — the
  fastest path for tests and research sessions;
- with a ``root`` it persists each table as Parquet (via ``pyarrow``) under
  ``root/<tier>/<table>.parquet``; when ``pyarrow`` is unavailable it falls
  back to pandas pickle files so the module always imports and works with
  only numpy+pandas installed;
- :meth:`query` lazily uses ``duckdb`` for SQL over the stored tables when
  the package is present (optional convenience, never required).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from quantos.data.schema.base import Schema
from quantos.data.store.base import TIERS, check_tier

__all__ = ["DuckDBStore"]

_SAFE_TABLE = re.compile(r"[^A-Za-z0-9_.-]+")


def _parquet_available() -> bool:
    """True when pyarrow can serve Parquet round-trips."""
    try:
        import pyarrow.parquet  # noqa: F401, PLC0415 — optional, probed lazily (I6)
    except ImportError:
        return False
    return True


def _sort_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Keep tables ordered by (symbol, event_time) when those columns exist."""
    keys = [c for c in ("symbol", "event_time") if c in df.columns]
    if keys:
        return df.sort_values(keys, kind="stable").reset_index(drop=True)
    return df.reset_index(drop=True)


class DuckDBStore:
    """Tiered store over Parquet files (or pure memory), satisfying ``Store``."""

    def __init__(self, root: str | Path | None = None) -> None:
        """
        Args:
            root: directory to persist under; ``None`` keeps everything in
                memory (per-process, ideal for tests and one-shot research).
        """
        self.root = Path(root).expanduser() if root is not None else None
        self._memory: dict[tuple[str, str], pd.DataFrame] = {}
        self._use_parquet = _parquet_available()
        if self.root is not None:
            for tier in TIERS:
                (self.root / tier).mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------

    def _path(self, tier: str, table: str) -> Path:
        assert self.root is not None
        safe = _SAFE_TABLE.sub("_", table)
        suffix = ".parquet" if self._use_parquet else ".pkl"
        return self.root / tier / f"{safe}{suffix}"

    # -- low-level frame IO --------------------------------------------------

    def _load(self, tier: str, table: str) -> pd.DataFrame:
        check_tier(tier)
        if self.root is None:
            return self._memory.get((tier, table), pd.DataFrame()).copy()
        path = self._path(tier, table)
        if not path.exists():
            return pd.DataFrame()
        if self._use_parquet:
            return pd.read_parquet(path)
        loaded = pd.read_pickle(path)  # noqa: S301 — own artifact, offline fallback
        assert isinstance(loaded, pd.DataFrame)
        return loaded

    def _save(self, tier: str, table: str, df: pd.DataFrame) -> None:
        check_tier(tier)
        if self.root is None:
            self._memory[(tier, table)] = df
            return
        path = self._path(tier, table)
        if self._use_parquet:
            df.to_parquet(path, index=False)
        else:
            df.to_pickle(path)

    # -- Store protocol -------------------------------------------------------

    def write(self, tier: str, table: str, df: pd.DataFrame, schema: Schema | None = None) -> int:
        """Append rows; returns the number of rows written."""
        if df.empty:
            return 0
        existing = self._load(tier, table)
        merged = df if existing.empty else pd.concat([existing, df], ignore_index=True)
        self._save(tier, table, _sort_frame(merged))
        return len(df)

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        """Insert-or-replace on ``keys``; idempotent. Returns net-new rows."""
        if df.empty:
            return 0
        existing = self._load(tier, table)
        before = len(existing)
        merged = df if existing.empty else pd.concat([existing, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=keys, keep="last")
        self._save(tier, table, _sort_frame(merged))
        return len(merged) - before

    def read(
        self,
        tier: str,
        table: str,
        symbol: str | None = None,
        start: Any | None = None,
        end: Any | None = None,
    ) -> pd.DataFrame:
        """Read a table, filtered by symbol and ``event_time`` window."""
        df = self._load(tier, table)
        if df.empty:
            return df
        if symbol is not None and "symbol" in df.columns:
            df = df[df["symbol"] == symbol]
        if "event_time" in df.columns:
            if start is not None:
                df = df[df["event_time"] >= pd.Timestamp(start)]
            if end is not None:
                df = df[df["event_time"] <= pd.Timestamp(end)]
        return df.reset_index(drop=True)

    def tables(self, tier: str) -> list[str]:
        """List tables present in a tier."""
        check_tier(tier)
        if self.root is None:
            return sorted(t for (tr, t) in self._memory if tr == tier)
        return sorted(p.stem for p in (self.root / tier).iterdir() if p.is_file())

    # -- optional SQL --------------------------------------------------------

    def query(self, sql: str, tier: str = "curated") -> pd.DataFrame:
        """Run ad-hoc SQL over a tier's tables via DuckDB (optional extra).

        Each table in the tier is registered under its own name. Raises a
        clear error when ``duckdb`` is not installed — it is never required
        by any core path (I6).
        """
        try:
            import duckdb  # noqa: PLC0415 — optional extra, lazy on purpose (I6)
        except ImportError as exc:  # pragma: no cover - exercised only without duckdb
            raise RuntimeError(
                "DuckDBStore.query needs the optional 'duckdb' package "
                "(pip install 'quantos[research]')"
            ) from exc
        conn = duckdb.connect()
        try:
            for table in self.tables(tier):
                conn.register(table, self._load(tier, table))
            return conn.execute(sql).df()
        finally:
            conn.close()

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary of what the store holds."""
        return {
            "backend": "parquet" if self._use_parquet else "pickle",
            "root": str(self.root) if self.root is not None else None,
            "tables": {tier: self.tables(tier) for tier in TIERS},
        }
