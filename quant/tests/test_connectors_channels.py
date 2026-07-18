"""WP-2.5 — channel connectors: schema conformance + determinism, offline."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.data.connectors import Connector, FetchRequest, registry
from quantos.data.connectors.news import tag_headline
from quantos.data.schema import DataValidator, schema_registry

CHANNEL_NAMES = ("derivatives", "onchain", "macro", "sentiment", "news")


def req(**overrides: object) -> FetchRequest:
    defaults: dict = {"symbol": "BTC/USDT", "limit": 100}
    defaults.update(overrides)
    return FetchRequest(**defaults)


@pytest.fixture(params=CHANNEL_NAMES)
def connector(request: pytest.FixtureRequest) -> Connector:
    return registry.get(request.param)


class TestEveryChannelConnector:
    def test_self_registered_with_matching_category(self, connector: Connector) -> None:
        assert connector.metadata.name == connector.metadata.category != "market"

    def test_synthetic_is_deterministic(self, connector: Connector) -> None:
        a = connector.synthetic(req()).rows
        b = connector.synthetic(req()).rows
        pd.testing.assert_frame_equal(a, b)

    def test_synthetic_differs_across_symbols_and_seeds(self, connector: Connector) -> None:
        base = connector.synthetic(req()).rows
        other_symbol = connector.synthetic(req(symbol="ETH/USDT")).rows
        other_seed = connector.synthetic(req(seed=7)).rows
        assert not base.drop(columns=["symbol"]).equals(other_symbol.drop(columns=["symbol"]))
        assert not base.equals(other_seed)

    def test_schema_valid_without_coercion(self, connector: Connector) -> None:
        rows = connector.synthetic(req()).rows
        schema = schema_registry.latest(connector.metadata.schema_name)
        _, report = DataValidator().validate(rows, schema, coerce=False)
        assert report.ok, f"{connector.metadata.name}: {report.errors}"

    def test_auto_mode_offline_is_synthetic_never_false_live(self, connector: Connector) -> None:
        result = connector.fetch(req(mode="auto"))
        assert result.source_mode == "synthetic"

    def test_live_mode_offline_raises(self, connector: Connector) -> None:
        with pytest.raises(RuntimeError):
            connector.fetch(req(mode="live"))

    def test_window_honoured(self, connector: Connector) -> None:
        result = connector.synthetic(
            req(start="2024-01-05 00:00+00:00", end="2024-01-20 00:00+00:00", limit=10)
        )
        assert len(result.rows) <= 10
        assert result.rows["event_time"].min() >= pd.Timestamp("2024-01-05", tz="UTC")
        assert result.rows["event_time"].max() <= pd.Timestamp("2024-01-20", tz="UTC")


class TestChannelSpecifics:
    def test_sentiment_score_in_range(self) -> None:
        rows = registry.get("sentiment").synthetic(req(limit=1000)).rows
        assert float(rows["score"].abs().max()) <= 1.0

    def test_derivatives_funding_within_sane_bounds(self) -> None:
        rows = registry.get("derivatives").synthetic(req(limit=1000)).rows
        assert float(rows["funding_rate"].abs().max()) <= 0.05

    def test_onchain_net_flow_is_inflow_minus_outflow(self) -> None:
        rows = registry.get("onchain").synthetic(req(limit=200)).rows
        expected = rows["inflow"] - rows["outflow"]
        pd.testing.assert_series_equal(
            rows["net_exchange_flow"], expected, check_names=False
        )

    def test_macro_carries_event_flags(self) -> None:
        rows = registry.get("macro").synthetic(req(limit=240)).rows
        assert rows["event_flag"].dtype.kind == "b"
        assert bool(rows["event_flag"].any())

    def test_news_keyword_tagger_is_deterministic_and_signed(self) -> None:
        tag, sentiment = tag_headline("Major exchange hack drains wallets")
        assert tag == "security" and sentiment < 0
        tag, sentiment = tag_headline("Spot ETF approval imminent")
        assert tag == "regulation" and sentiment > 0
        assert tag_headline("Nothing notable happened") == ("general", 0.0)

    def test_news_ids_unique_per_symbol_window(self) -> None:
        rows = registry.get("news").synthetic(req(limit=200)).rows
        assert not rows.duplicated(subset=["symbol", "event_time", "news_id"]).any()
