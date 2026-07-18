"""WP-2.7 — 24/7 operations: gap repair, offline scheduler, health monitor."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.data.connectors import FetchRequest, registry
from quantos.data.ingest import (
    IngestionRunner,
    RetryPolicy,
    Scheduler,
    detect_gaps,
    missing_ranges,
    repair_gaps,
)
from quantos.data.quality import HealthMonitor
from quantos.data.store import DuckDBStore

UTC = "UTC"


def make_runner(monitor: HealthMonitor | None = None) -> IngestionRunner:
    return IngestionRunner(
        DuckDBStore(),
        monitor=monitor,
        retry=RetryPolicy(max_attempts=2, jitter=False),
        sleep=lambda _s: None,
    )


class TestGapDetection:
    def test_complete_series_has_no_gaps(self) -> None:
        times = pd.date_range("2024-01-01", periods=24, freq="1h", tz=UTC)
        assert len(detect_gaps(times, 3600)) == 0

    def test_missing_timestamps_are_detected(self) -> None:
        times = pd.date_range("2024-01-01", periods=24, freq="1h", tz=UTC)
        holed = times.delete([5, 6, 10])
        gaps = detect_gaps(holed, 3600)
        assert list(gaps) == [times[5], times[6], times[10]]

    def test_missing_ranges_groups_contiguous(self) -> None:
        times = pd.date_range("2024-01-01", periods=24, freq="1h", tz=UTC)
        gaps = detect_gaps(times.delete([5, 6, 10]), 3600)
        ranges = missing_ranges(gaps, 3600)
        assert ranges == [(times[5], times[6]), (times[10], times[10])]


class TestGapRepair:
    def test_injected_gap_is_detected_and_repaired(self) -> None:
        # Ingest two disjoint windows, leaving a hole between them, then
        # repair. The backfilled rows must carry the canonical values (I8).
        runner = make_runner()
        market = registry.get("market")
        base = {"symbol": "BTC/USDT", "timeframe": "1h", "mode": "synthetic", "limit": 500}
        runner.run(
            market,
            FetchRequest(start="2024-01-01 00:00+00:00", end="2024-01-01 12:00+00:00", **base),
        )
        runner.run(
            market,
            FetchRequest(start="2024-01-02 00:00+00:00", end="2024-01-02 12:00+00:00", **base),
            use_watermark=False,
        )
        curated = runner.store.read("curated", "market", symbol="BTC/USDT")
        assert len(detect_gaps(curated["event_time"], 3600)) == 11

        summary = repair_gaps(runner, market, FetchRequest(**base))
        assert summary["gaps_found"] == 11
        assert summary["gaps_remaining"] == 0

        repaired = runner.store.read("curated", "market", symbol="BTC/USDT")
        assert len(detect_gaps(repaired["event_time"], 3600)) == 0
        # backfilled values match a fresh canonical fetch bit-for-bit
        full = market.synthetic(
            FetchRequest(
                start="2024-01-01 00:00+00:00", end="2024-01-02 12:00+00:00", **base
            )
        ).rows
        merged = repaired.merge(
            full, on=["symbol", "timeframe", "event_time"], suffixes=("", "_ref")
        )
        assert (merged["close"] == merged["close_ref"]).all()

    def test_repair_does_not_regress_watermark(self) -> None:
        runner = make_runner()
        market = registry.get("market")
        base = {"symbol": "BTC/USDT", "timeframe": "1h", "mode": "synthetic", "limit": 500}
        runner.run(
            market,
            FetchRequest(start="2024-01-03 00:00+00:00", end="2024-01-03 06:00+00:00", **base),
        )
        high_mark = runner.watermarks.get("market", "BTC/USDT")
        runner.run(
            market,
            FetchRequest(start="2024-01-01 00:00+00:00", end="2024-01-01 06:00+00:00", **base),
            use_watermark=False,
        )
        assert runner.watermarks.get("market", "BTC/USDT") == high_mark


class TestScheduler:
    def test_run_due_dispatches_only_due_jobs(self) -> None:
        runner = make_runner()
        scheduler = Scheduler(runner)
        t0 = pd.Timestamp("2024-02-01 00:00", tz=UTC)
        scheduler.add("market", "BTC/USDT", mode="synthetic", start_at=t0)
        scheduler.add(
            "sentiment",
            "BTC/USDT",
            mode="synthetic",
            start_at=t0 + pd.Timedelta(hours=6),
        )

        reports = scheduler.run_due(t0)
        assert set(reports) == {"market:BTC/USDT"}  # sentiment not yet due
        assert reports["market:BTC/USDT"].ok

        # immediately re-running dispatches nothing: next_due advanced
        assert scheduler.run_due(t0) == {}

        later = t0 + pd.Timedelta(hours=6)
        reports = scheduler.run_due(later)
        assert set(reports) == {"market:BTC/USDT", "sentiment:BTC/USDT"}

    def test_next_due_stays_aligned_after_missed_windows(self) -> None:
        runner = make_runner()
        scheduler = Scheduler(runner)
        t0 = pd.Timestamp("2024-02-01 00:00", tz=UTC)
        job = scheduler.add("market", "BTC/USDT", mode="synthetic", start_at=t0)
        # the loop was down for 10 hours; the job fires once and realigns
        late = t0 + pd.Timedelta(hours=10)
        assert set(scheduler.run_due(late)) == {"market:BTC/USDT"}
        assert job.next_due is not None and job.next_due > late

    def test_unknown_connector_rejected_at_add(self) -> None:
        scheduler = Scheduler(make_runner())
        with pytest.raises(KeyError):
            scheduler.add("nope", "BTC/USDT")


class TestHealthMonitor:
    def test_runner_feeds_monitor_and_freshness_is_computed(self) -> None:
        monitor = HealthMonitor()
        runner = make_runner(monitor)
        market = registry.get("market")
        runner.run(
            market,
            FetchRequest(
                symbol="BTC/USDT",
                timeframe="1h",
                mode="synthetic",
                start="2024-01-01 00:00+00:00",
                end="2024-01-02 00:00+00:00",
                limit=100,
            ),
        )
        fresh_now = pd.Timestamp("2024-01-02 01:00", tz=UTC)
        status = monitor.status("market", 3600, now=fresh_now)
        assert status["healthy"] and not status["stale"]
        assert status["lag_seconds"] == 3600.0
        assert status["success_rate"] == 1.0
        assert status["last_source_mode"] == "synthetic"

    def test_stale_connector_is_flagged(self) -> None:
        monitor = HealthMonitor(stale_after=3.0)
        monitor.record_success(
            "market",
            rows=10,
            last_event_time=pd.Timestamp("2024-01-01 00:00", tz=UTC),
            source_mode="synthetic",
        )
        much_later = pd.Timestamp("2024-01-01 04:00", tz=UTC)  # 4 cadences behind
        status = monitor.status("market", 3600, now=much_later)
        assert status["stale"] and not status["healthy"]

    def test_failures_lower_success_rate_and_carry_last_error(self) -> None:
        monitor = HealthMonitor()
        monitor.record_success(
            "x", rows=5, last_event_time=pd.Timestamp("2024-01-01", tz=UTC), source_mode="live"
        )
        monitor.record_failure("x", error="timeout")
        status = monitor.status("x", 60, now=pd.Timestamp("2024-01-01 00:01", tz=UTC))
        assert status["success_rate"] == 0.5
        assert status["last_error"] == "timeout"
        assert not status["healthy"]

    def test_report_covers_registry_cadences(self) -> None:
        monitor = HealthMonitor()
        cadences = {"market": 3600, "news": 21600}
        report = monitor.report(cadences, now=pd.Timestamp("2024-01-01", tz=UTC))
        assert set(report) == {"market", "news"}
        assert report["market"]["stale"] is True  # never ingested -> stale
