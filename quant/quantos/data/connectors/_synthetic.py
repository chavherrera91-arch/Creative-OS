"""Shared helpers for deterministic synthetic connector data (I6, I8).

Every synthetic connector generates a *canonical* series — a fixed-length
grid anchored at a fixed epoch, produced by a seeded generator — and then
slices the requested window out of it. Because the canonical series is a pure
function of (connector, symbol, seed), re-fetching any sub-window always
reproduces exactly the same values: ingestion stays idempotent and gap repair
reconstructs precisely the missing rows.
"""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from quantos.data.connectors.base import FetchRequest

__all__ = [
    "CANONICAL_PERIODS",
    "SYNTHETIC_EPOCH",
    "cadence_index",
    "derive_seed",
    "rng_for",
    "slice_window",
]

#: Fixed anchor for all synthetic series — no wall clock in research paths (I8).
SYNTHETIC_EPOCH = "2024-01-01"

#: Length of every canonical synthetic series.
CANONICAL_PERIODS = 1440


def derive_seed(name: str, symbol: str, seed: int) -> int:
    """Per-(connector, symbol) seed derived from the global seed (I8)."""
    return (zlib.crc32(f"{name}|{symbol}".encode()) ^ seed) & 0xFFFFFFFF


def rng_for(name: str, symbol: str, seed: int) -> np.random.Generator:
    """Seeded generator for one connector/symbol pair."""
    return np.random.default_rng(derive_seed(name, symbol, seed))


def cadence_index(cadence_seconds: int, periods: int = CANONICAL_PERIODS) -> pd.DatetimeIndex:
    """The canonical UTC event-time grid for a cadence."""
    return pd.date_range(
        SYNTHETIC_EPOCH, periods=periods, freq=pd.Timedelta(seconds=cadence_seconds), tz="UTC"
    )


def slice_window(rows: pd.DataFrame, req: FetchRequest) -> pd.DataFrame:
    """Slice a canonical frame to the request's [start, end] window and limit.

    The last ``req.limit`` rows of the window are kept (most recent data is
    the interesting part for research).
    """
    out = rows
    if req.start is not None:
        out = out[out["event_time"] >= pd.Timestamp(req.start)]
    if req.end is not None:
        out = out[out["event_time"] <= pd.Timestamp(req.end)]
    return out.tail(req.limit).reset_index(drop=True)
