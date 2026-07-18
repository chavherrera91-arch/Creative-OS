"""WP-2.8 — DataLake facade: ingest, snapshot (0 abstentions), health, catalog."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.committee.committee import default_committee
from quantos.data.connectors import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
    register,
    registry,
)
from quantos.data.lake import DataLake
from quantos.data.schema import FieldSpec, Schema, schema_registry

SYMBOL = "BTC/USDT"


@pytest.fixture()
def lake() -> DataLake:
    return DataLake()  # in-memory store, module registries


@pytest.fixture()
def ingested(lake: DataLake) -> DataLake:
    reports = lake.ingest(SYMBOL, mode="synthetic")
    assert all(r.ok for r in reports.values())
    return lake


class TestIngest:
    def test_every_registered_connector_reports(self, lake: DataLake) -> None:
        reports = lake.ingest(SYMBOL, mode="synthetic")
        assert set(reports) >= {"market", "derivatives", "onchain", "macro", "sentiment", "news"}
        assert all(r.ok for r in reports.values())

    def test_ingest_twice_is_idempotent_end_to_end(self, lake: DataLake) -> None:
        # Acceptance §7.3: identical curated row counts after a second run.
        lake.ingest(SYMBOL, mode="synthetic")
        counts = {t: len(lake.store.read("curated", t)) for t in lake.store.tables("curated")}
        lake.ingest(SYMBOL, mode="synthetic")
        again = {t: len(lake.store.read("curated", t)) for t in lake.store.tables("curated")}
        assert counts == again

    def test_category_subset(self, lake: DataLake) -> None:
        reports = lake.ingest(SYMBOL, mode="synthetic", categories=["market"])
        assert set(reports) == {"market"}


class TestSnapshot:
    def test_snapshot_before_ingest_raises(self, lake: DataLake) -> None:
        with pytest.raises(ValueError):
            lake.snapshot(SYMBOL)

    def test_snapshot_carries_all_channels(self, ingested: DataLake) -> None:
        snapshot = ingested.snapshot(SYMBOL)
        assert snapshot.bars >= 60
        for channel in ("derivatives", "onchain", "macro", "sentiment"):
            assert snapshot.has(channel), f"channel {channel} missing"

    def test_committee_deliberates_with_zero_abstentions(self, ingested: DataLake) -> None:
        # Acceptance §7.6: after ingest, every analyst has data to work with.
        snapshot = ingested.snapshot(SYMBOL)
        decision = default_committee().deliberate(snapshot)
        abstained = [o.analyst for o in decision.opinions if o.abstained]
        assert abstained == []
        assert decision.confidence_report.abstentions == []
        assert decision.confidence_report.n_active == len(decision.opinions)

    def test_historical_at_is_point_in_time(self, ingested: DataLake) -> None:
        at = pd.Timestamp("2024-02-01 00:00", tz="UTC")
        snapshot = ingested.snapshot(SYMBOL, at=at)
        assert pd.Timestamp(snapshot.ohlcv.index.max()) <= at
        # the same moment always rebuilds the same snapshot (I8)
        again = ingested.snapshot(SYMBOL, at=at)
        pd.testing.assert_frame_equal(snapshot.ohlcv, again.ohlcv)
        assert snapshot.sentiment == again.sentiment

    def test_news_never_from_the_future(self, ingested: DataLake) -> None:
        at = pd.Timestamp("2024-02-01 00:00", tz="UTC")
        snapshot = ingested.snapshot(SYMBOL, at=at)
        assert snapshot.news, "expected headlines at or before `at`"
        assert all(pd.Timestamp(n["time"]) <= at for n in snapshot.news)


class TestObservability:
    def test_health_reports_per_connector_freshness(self, ingested: DataLake) -> None:
        # Acceptance §7.7: freshness + success per connector.
        now = pd.Timestamp("2024-03-01 12:00", tz="UTC")
        health = ingested.health(now=now)
        for name in ("market", "derivatives", "onchain", "macro", "sentiment", "news"):
            entry = health[name]
            assert entry["runs"] >= 1
            assert entry["success_rate"] == 1.0
            assert entry["lag_seconds"] is not None
            assert entry["circuit"]["state"] == "closed"

    def test_catalog_lists_datasets_with_schema_and_coverage(self, ingested: DataLake) -> None:
        catalog = ingested.catalog()
        entries = {d["dataset"]: d for d in catalog.datasets()}
        assert "market" in entries
        market = entries["market"]
        assert market["schema_version"] == 1
        assert market["rows"] > 0
        assert market["last_event_time"] is not None
        assert market["category"] == "market"
        assert "_watermarks" not in entries

    def test_repair_gaps_reports_clean_lake(self, ingested: DataLake) -> None:
        summaries = ingested.repair_gaps(SYMBOL, mode="synthetic")
        assert all(s["gaps_remaining"] == 0 for s in summaries.values())


DUMMY_SCHEMA = Schema(
    name="orderbook_imbalance",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime"),
        FieldSpec("ingested_at", "datetime"),
        FieldSpec("imbalance", "float64", min=-1.0, max=1.0),
    ),
    primary_key=("symbol", "event_time"),
)


class TestZeroCoreEdits:
    def test_new_connector_flows_end_to_end_without_core_edits(self) -> None:
        # Acceptance §7.1: this test is the ONLY code written to add a brand
        # new source. base.py, registry.py and lake.py are untouched; the
        # connector registers itself and the lake discovers it.
        schema_registry.register(DUMMY_SCHEMA)

        @register
        class OrderbookImbalanceConnector(Connector):
            metadata = ConnectorMetadata(
                name="orderbook_imbalance",
                category="market",
                schema_name="orderbook_imbalance",
                cadence_seconds=3600,
            )

            def fetch(self, req: FetchRequest) -> FetchResult:
                return self.synthetic(req)

            def synthetic(self, req: FetchRequest) -> FetchResult:
                times = pd.date_range("2024-01-01", periods=48, freq="1h", tz="UTC")
                rows = pd.DataFrame(
                    {
                        "symbol": [req.symbol] * 48,
                        "event_time": times,
                        "ingested_at": times,
                        "imbalance": [((i % 21) - 10) / 10.0 for i in range(48)],
                    }
                )
                return FetchResult(rows=rows, schema_version=1, source_mode="synthetic")

        try:
            lake = DataLake()
            reports = lake.ingest(SYMBOL, mode="synthetic")
            assert reports["orderbook_imbalance"].ok
            curated = lake.store.read("curated", "orderbook_imbalance", symbol=SYMBOL)
            assert len(curated) == 48
            # ...and it is immediately point-in-time readable (I2)
            value = lake.features.as_of(
                SYMBOL, "2024-01-01 05:00+00:00", ["orderbook_imbalance.imbalance"]
            )
            assert value == {"orderbook_imbalance.imbalance": -0.5}
            # ...and observable
            assert "orderbook_imbalance" in lake.health(
                now=pd.Timestamp("2024-01-03", tz="UTC")
            )
        finally:
            registry.unregister("orderbook_imbalance")


class TestChannelsAgainstDeliberation:
    def test_snapshot_serialises(self, ingested: DataLake) -> None:
        payload = ingested.snapshot(SYMBOL).as_dict()
        assert payload["channels"]["macro"] and payload["channels"]["sentiment"]
