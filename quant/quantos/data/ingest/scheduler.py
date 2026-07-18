"""Interval scheduler for 24/7 ingestion (DATA_INFRASTRUCTURE §5).

The scheduler holds ``(connector, symbol, cadence)`` jobs and dispatches the
due ones to the :class:`IngestionRunner`. The offline/default path is
:meth:`Scheduler.run_due` with an explicit ``now`` — fully testable without
a running loop, wall clock or thread (I6). Production may wrap it in
APScheduler/cron; the semantics stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.data.connectors.base import FetchRequest
from quantos.data.connectors.registry import ConnectorRegistry
from quantos.data.connectors.registry import registry as default_registry
from quantos.data.ingest.runner import IngestionRunner
from quantos.data.schema.validation import ValidationReport

__all__ = ["Job", "Scheduler"]


@dataclass
class Job:
    """One recurring ingestion job.

    Attributes:
        connector: registered connector name.
        symbol: symbol to ingest.
        timeframe: bar timeframe passed through to the request.
        cadence_seconds: how often the job runs.
        mode: fetch mode for the requests (``auto`` by default).
        seed: synthetic seed passed through (I8).
        next_due: when the job should next run; ``None`` = due immediately.
    """

    connector: str
    symbol: str
    timeframe: str = "1h"
    cadence_seconds: int = 3600
    mode: str = "auto"
    seed: int = 42
    next_due: pd.Timestamp | None = field(default=None)

    @property
    def key(self) -> str:
        """Stable identifier for reports."""
        return f"{self.connector}:{self.symbol}"

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "connector": self.connector,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "cadence_seconds": self.cadence_seconds,
            "mode": self.mode,
            "next_due": str(self.next_due) if self.next_due is not None else None,
        }


class Scheduler:
    """Dispatches due jobs to the runner; discovery via the registry (I7)."""

    def __init__(
        self, runner: IngestionRunner, registry: ConnectorRegistry | None = None
    ) -> None:
        self.runner = runner
        self.registry = registry or default_registry
        self.jobs: list[Job] = []

    def add(
        self,
        connector: str,
        symbol: str,
        *,
        timeframe: str = "1h",
        cadence_seconds: int | None = None,
        mode: str = "auto",
        seed: int = 42,
        start_at: pd.Timestamp | None = None,
    ) -> Job:
        """Register a recurring job (cadence defaults to the connector's)."""
        meta = self.registry.get(connector).metadata  # validates the name early
        job = Job(
            connector=connector,
            symbol=symbol,
            timeframe=timeframe,
            cadence_seconds=cadence_seconds or meta.cadence_seconds,
            mode=mode,
            seed=seed,
            next_due=start_at,
        )
        self.jobs.append(job)
        return job

    def due(self, now: pd.Timestamp) -> list[Job]:
        """Jobs whose ``next_due`` has arrived (or was never set)."""
        return [j for j in self.jobs if j.next_due is None or j.next_due <= now]

    def run_due(self, now: pd.Timestamp) -> dict[str, ValidationReport]:
        """Run every due job once and advance its ``next_due``.

        The next due time stays aligned to the cadence grid (skipped windows
        do not drift the schedule); a failing job still advances so one dead
        source can never busy-loop the scheduler.

        Returns:
            ``{job.key: report}`` for the jobs that ran.
        """
        reports: dict[str, ValidationReport] = {}
        for job in self.due(now):
            connector = self.registry.get(job.connector)
            req = FetchRequest(
                symbol=job.symbol,
                end=now,
                timeframe=job.timeframe,
                mode=job.mode,
                seed=job.seed,
            )
            reports[job.key] = self.runner.run(connector, req)
            step = pd.Timedelta(seconds=job.cadence_seconds)
            job.next_due = (job.next_due or now) + step
            while job.next_due <= now:
                job.next_due += step
        return reports

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot of the schedule."""
        return {"jobs": [j.as_dict() for j in self.jobs]}
