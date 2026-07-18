"""Point-in-time-correct feature reads (invariant I2).

``FeatureStore.as_of`` performs a backward as-of lookup across curated
tables: for a moment ``at`` it returns the latest value whose ``event_time``
is **less than or equal to** ``at`` — never a later one. This is the single
mechanism that keeps research, backtests and ML free of look-ahead.

Features are addressed as ``"table.column"``, e.g.
``"derivatives.funding_rate"`` or ``"market.close"``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantos.data.store.base import Store

__all__ = ["FeatureStore"]


def _native(value: Any) -> Any:
    """Convert numpy scalars to plain Python for clean serialisation (I4)."""
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _parse(feature: str) -> tuple[str, str]:
    """Split ``"table.column"`` into its parts."""
    table, sep, column = feature.partition(".")
    if not sep or not table or not column:
        raise ValueError(f"feature {feature!r} must be addressed as 'table.column'")
    return table, column


class FeatureStore:
    """As-of reads over the curated tier."""

    def __init__(self, store: Store, time_column: str = "event_time") -> None:
        self.store = store
        self.time_column = time_column

    def as_of(
        self, symbol: str, at: pd.Timestamp | str, features: list[str]
    ) -> dict[str, Any]:
        """Latest value of each feature with ``event_time <= at`` (I2).

        Args:
            symbol: which symbol's rows to read.
            at: the point in time of the read.
            features: ``"table.column"`` names.

        Returns:
            ``{feature: value}``. A feature with no row at or before ``at``
            is simply absent — an honest gap, never a fabricated (or future)
            value.
        """
        at = pd.Timestamp(at)
        wanted: dict[str, list[str]] = {}
        for feature in features:
            table, column = _parse(feature)
            wanted.setdefault(table, []).append(column)

        values: dict[str, Any] = {}
        for table, columns in wanted.items():
            frame = self.store.read("curated", table, symbol=symbol, end=at)
            if frame.empty:
                continue
            frame = frame.sort_values(self.time_column, kind="stable")
            last = frame.iloc[-1]
            assert pd.Timestamp(last[self.time_column]) <= at  # the I2 guarantee
            for column in columns:
                if column in frame.columns:
                    values[f"{table}.{column}"] = _native(last[column])
        return values

    def frame(
        self,
        symbol: str,
        start: pd.Timestamp | str,
        end: pd.Timestamp | str,
        features: list[str],
        freq: str = "1h",
    ) -> pd.DataFrame:
        """A regular-grid frame of backward as-of feature values (I2).

        Every cell at grid time *t* holds the latest value with
        ``event_time <= t``; cells before a feature's first observation are
        NaN. Built with ``merge_asof`` (backward), so no future value can
        leak into any row.
        """
        grid = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=freq)
        out = pd.DataFrame(index=grid)
        out.index.name = self.time_column

        wanted: dict[str, list[str]] = {}
        for feature in features:
            table, column = _parse(feature)
            wanted.setdefault(table, []).append(column)

        base = pd.DataFrame({self.time_column: grid})
        for table, columns in wanted.items():
            frame = self.store.read("curated", table, symbol=symbol, end=end)
            if frame.empty:
                for column in columns:
                    out[f"{table}.{column}"] = np.nan
                continue
            frame = frame.sort_values(self.time_column, kind="stable")
            present = [c for c in columns if c in frame.columns]
            joined = pd.merge_asof(
                base,
                frame[[self.time_column, *present]],
                on=self.time_column,
                direction="backward",
            )
            for column in columns:
                key = f"{table}.{column}"
                if column in present:
                    out[key] = joined[column].to_numpy()
                else:
                    out[key] = np.nan
        return out
