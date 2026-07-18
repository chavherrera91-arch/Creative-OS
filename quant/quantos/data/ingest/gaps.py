"""Gap detection and backfill (24/7 operation, DATA_INFRASTRUCTURE §5).

A connector's cadence defines the expected event-time grid; any expected
timestamp missing from the curated tier is a gap. Repair re-fetches the
missing windows through the runner's backfill path (watermark ignored so the
history can be filled; the watermark itself never regresses).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pandas as pd

from quantos.data.connectors.base import Connector, FetchRequest
from quantos.data.ingest.runner import IngestionRunner

__all__ = ["detect_gaps", "expected_grid", "missing_ranges", "repair_gaps"]


def expected_grid(
    start: pd.Timestamp, end: pd.Timestamp, cadence_seconds: int
) -> pd.DatetimeIndex:
    """The expected event-time grid between two stamps at a cadence."""
    return pd.date_range(start, end, freq=pd.Timedelta(seconds=cadence_seconds))


def detect_gaps(
    times: pd.Series | pd.DatetimeIndex,
    cadence_seconds: int,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DatetimeIndex:
    """Expected timestamps missing from an observed series.

    Args:
        times: observed event times (one symbol's curated rows).
        cadence_seconds: the connector's cadence.
        start: grid start; defaults to the first observed stamp.
        end: grid end; defaults to the last observed stamp.

    Returns:
        The missing timestamps (empty when the series is complete or empty).
    """
    index = pd.DatetimeIndex(times).unique().sort_values()
    if len(index) == 0:
        return pd.DatetimeIndex([], tz="UTC")
    grid = expected_grid(start or index[0], end or index[-1], cadence_seconds)
    return grid.difference(index)


def missing_ranges(
    gaps: pd.DatetimeIndex, cadence_seconds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Group missing timestamps into contiguous [start, end] windows."""
    if len(gaps) == 0:
        return []
    step = pd.Timedelta(seconds=cadence_seconds)
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    run_start = prev = gaps[0]
    for stamp in gaps[1:]:
        if stamp - prev > step:
            ranges.append((run_start, prev))
            run_start = stamp
        prev = stamp
    ranges.append((run_start, prev))
    return ranges


def repair_gaps(
    runner: IngestionRunner,
    connector: Connector,
    req: FetchRequest,
) -> dict[str, Any]:
    """Detect and backfill gaps in one connector's curated history.

    Args:
        runner: the ingestion runner (its store/validator are reused).
        connector: the source to repair.
        req: template request — symbol/timeframe/mode/seed are honoured; the
            window is derived per detected gap.

    Returns:
        A summary dict: gaps found, repair windows, gaps remaining.
    """
    name = connector.metadata.name
    cadence = connector.metadata.cadence_seconds
    schema = runner.schemas.latest(connector.metadata.schema_name)
    curated = runner.store.read("curated", name, symbol=req.symbol)
    times = (
        curated[schema.time_column] if not curated.empty else pd.DatetimeIndex([], tz="UTC")
    )
    gaps = detect_gaps(times, cadence)
    ranges = missing_ranges(gaps, cadence)
    for window_start, window_end in ranges:
        window_req = dataclasses.replace(
            req,
            start=window_start,
            end=window_end,
            limit=max(req.limit, len(gaps) + 1),
        )
        runner.run(connector, window_req, use_watermark=False)

    remaining = detect_gaps(
        runner.store.read("curated", name, symbol=req.symbol)[schema.time_column]
        if not curated.empty
        else times,
        cadence,
    )
    return {
        "connector": name,
        "symbol": req.symbol,
        "gaps_found": int(len(gaps)),
        "windows_repaired": [(str(s), str(e)) for s, e in ranges],
        "gaps_remaining": int(len(remaining)),
    }
