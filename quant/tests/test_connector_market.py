"""WP-2.4 — market connector: deterministic, schema-valid, honest labelling."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.data.connectors import FetchRequest, registry
from quantos.data.connectors.market import MARKET_SCHEMA, MarketConnector
from quantos.data.schema import DataValidator, schema_registry


@pytest.fixture()
def connector() -> MarketConnector:
    return MarketConnector()


def req(**overrides: object) -> FetchRequest:
    defaults: dict = {"symbol": "BTC/USDT", "timeframe": "1h", "limit": 200}
    defaults.update(overrides)
    return FetchRequest(**defaults)


class TestDiscovery:
    def test_market_connector_is_self_registered(self) -> None:
        assert registry.get("market").metadata.category == "market"

    def test_market_schema_is_registered(self) -> None:
        assert schema_registry.latest("market") == MARKET_SCHEMA


class TestSynthetic:
    def test_deterministic(self, connector: MarketConnector) -> None:
        a = connector.synthetic(req()).rows
        b = connector.synthetic(req()).rows
        pd.testing.assert_frame_equal(a, b)

    def test_schema_valid_without_coercion(self, connector: MarketConnector) -> None:
        rows = connector.synthetic(req()).rows
        _, report = DataValidator().validate(rows, MARKET_SCHEMA, coerce=False)
        assert report.ok, report.errors

    def test_window_and_limit_honoured(self, connector: MarketConnector) -> None:
        result = connector.synthetic(
            req(start="2024-01-02 00:00+00:00", end="2024-01-03 00:00+00:00", limit=10)
        )
        rows = result.rows
        assert len(rows) == 10
        assert rows["event_time"].min() >= pd.Timestamp("2024-01-02", tz="UTC")
        assert rows["event_time"].max() <= pd.Timestamp("2024-01-03", tz="UTC")

    def test_subwindow_refetch_reproduces_same_values(self, connector: MarketConnector) -> None:
        # Critical for idempotent ingestion + gap repair: a later fetch of a
        # sub-window must carry exactly the values of the original fetch.
        full = connector.synthetic(req(limit=1440)).rows
        window = connector.synthetic(
            req(start="2024-01-05 00:00+00:00", end="2024-01-06 00:00+00:00", limit=25)
        ).rows
        merged = window.merge(full, on=["symbol", "timeframe", "event_time"], suffixes=("", "_f"))
        assert len(merged) == len(window)
        for col in ("open", "high", "low", "close", "volume"):
            assert (merged[col] == merged[f"{col}_f"]).all()


class TestModes:
    def test_auto_mode_offline_labels_synthetic(self, connector: MarketConnector) -> None:
        result = connector.fetch(req(mode="auto"))
        assert result.source_mode == "synthetic"  # never a false "live" label
        assert result.schema_version == MARKET_SCHEMA.version

    def test_live_mode_offline_raises(self, connector: MarketConnector) -> None:
        with pytest.raises(RuntimeError):
            connector.fetch(req(mode="live"))

    def test_healthcheck(self, connector: MarketConnector) -> None:
        status = connector.healthcheck()
        assert status.healthy and status.last_success is not None
