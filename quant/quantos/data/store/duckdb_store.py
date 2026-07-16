"""Offline-default store: Parquet-backed, DuckDB-queryable.

Persists each ``tier.table`` as a Parquet file (via pyarrow) under a root
directory, or keeps everything in memory when no root is given (handy for
tests). DuckDB, when present, powers the optional :meth:`DuckDBStore.query` SQL
interface over the Parquet tables. Everything degrades gracefully: if no Parquet
engine is installed the store falls back to pickle, so the module always imports
and round-trips with only numpy+pandas (invariant I6).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantos.data.store.base import validate_tier

_TIME_COL = "event_time"


def _parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except Exception:
        try:
            import fastparquet  # noqa: F401

            return True
        except Exception:
            return False


class DuckDBStore:
    """Tiered table store over Parquet (in-memory when ``root`` is None)."""

    is_persistent: bool

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else None
        self.is_persistent = self.root is not None
        self._use_parquet = _parquet_available()
        self._ext = "parquet" if self._use_parquet else "pkl"
        self._mem: dict[tuple[str, str], pd.DataFrame] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    # -- Store protocol -------------------------------------------------------
    def write(self, tier: str, table: str, df: pd.DataFrame) -> int:
        validate_tier(tier)
        existing = self._load(tier, table)
        combined = df if existing is None else pd.concat([existing, df], ignore_index=True)
        self._save(tier, table, combined)
        return len(df)

    def upsert(self, tier: str, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        validate_tier(tier)
        existing = self._load(tier, table)
        combined = df if existing is None else pd.concat([existing, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=keys, keep="last")
        if _TIME_COL in combined.columns:
            sort_cols = (["symbol", _TIME_COL] if "symbol" in combined.columns else [_TIME_COL])
            combined = combined.sort_values(sort_cols, kind="stable")
        combined = combined.reset_index(drop=True)
        self._save(tier, table, combined)
        return len(combined)

    def read(
        self,
        tier: str,
        table: str,
        symbol: str | None = None,
        start=None,
        end=None,
    ) -> pd.DataFrame:
        validate_tier(tier)
        df = self._load(tier, table)
        if df is None:
            return pd.DataFrame()
        df = df.copy()
        if symbol is not None and "symbol" in df.columns:
            df = df[df["symbol"] == symbol]
        if _TIME_COL in df.columns:
            if start is not None:
                df = df[df[_TIME_COL] >= pd.Timestamp(start, tz="UTC")]
            if end is not None:
                df = df[df[_TIME_COL] <= pd.Timestamp(end, tz="UTC")]
        return df.reset_index(drop=True)

    def tables(self, tier: str) -> list[str]:
        validate_tier(tier)
        if self.root is None:
            return sorted(t for (ti, t) in self._mem if ti == tier)
        tier_dir = self.root / tier
        if not tier_dir.exists():
            return []
        return sorted(p.stem for p in tier_dir.glob(f"*.{self._ext}"))

    # -- optional DuckDB SQL --------------------------------------------------
    def query(self, sql: str) -> pd.DataFrame:
        """Run SQL over the tables via DuckDB. Reference tables as ``tier.table``
        will not work directly; instead register frames by name. Provided for
        analytical/research use; raises if DuckDB is unavailable."""
        import duckdb

        con = duckdb.connect()
        try:
            for (tier, table), _ in self._iter_all():
                frame = self._load(tier, table)
                if frame is not None:
                    con.register(f"{tier}__{table}", frame)
            return con.execute(sql).df()
        finally:
            con.close()

    # -- internals ------------------------------------------------------------
    def _path(self, tier: str, table: str) -> Path:
        assert self.root is not None
        return self.root / tier / f"{table}.{self._ext}"

    def _load(self, tier: str, table: str) -> pd.DataFrame | None:
        if self.root is None:
            return self._mem.get((tier, table))
        path = self._path(tier, table)
        if not path.exists():
            return None
        if self._use_parquet:
            return pd.read_parquet(path)
        return pd.read_pickle(path)

    def _save(self, tier: str, table: str, df: pd.DataFrame) -> None:
        if self.root is None:
            self._mem[(tier, table)] = df.reset_index(drop=True)
            return
        path = self._path(tier, table)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._use_parquet:
            df.to_parquet(path, index=False)
        else:
            df.to_pickle(path)

    def _iter_all(self):
        if self.root is None:
            for key in self._mem:
                yield key, None
        else:
            for tier in ("raw", "curated", "features"):
                for table in self.tables(tier):
                    yield (tier, table), None
