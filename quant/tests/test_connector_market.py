import pandas as pd

from quantos.data.connectors import registry
from quantos.data.connectors.base import FetchRequest
from quantos.data.connectors.market import MARKET_SCHEMA, MarketConnector
from quantos.data.schema import DataValidator, schema_registry


def test_market_connector_self_registered():
    # Importing quantos.data.connectors pulls in builtins -> market.
    import quantos.data.connectors  # noqa: F401

    assert "market" in registry.names()
    assert registry.get("market").metadata.category == "market"


def test_market_schema_registered():
    assert "market" in schema_registry.names()
    assert schema_registry.latest("market").version == MARKET_SCHEMA.version


def test_synthetic_is_deterministic_and_schema_valid():
    conn = MarketConnector()
    req = FetchRequest(symbol="BTC/USDT", timeframe="1h", limit=200, seed=7)
    a = conn.synthetic(req)
    b = conn.synthetic(req)

    assert a.source_mode == "synthetic"
    assert a.schema_version == MARKET_SCHEMA.version
    assert a.rows["close"].equals(b.rows["close"])  # deterministic with seed

    cleaned, report = DataValidator().validate(a.rows, MARKET_SCHEMA)
    assert report.ok, report.errors
    assert report.rows == 200


def test_columns_and_pit_fields():
    conn = MarketConnector()
    rows = conn.synthetic(FetchRequest(symbol="ETH/USDT", limit=10)).rows
    assert list(rows.columns) == [
        "symbol", "event_time", "ingested_at", "open", "high", "low", "close", "volume",
    ]
    # event_time (when true) is distinct from ingested_at (when stored) — I2.
    assert rows["event_time"].dt.tz is not None
    assert rows["ingested_at"].dt.tz is not None


def test_fetch_auto_falls_back_offline():
    # ccxt is not installed here, so auto mode must fall back to synthetic.
    conn = MarketConnector(source="auto")
    result = conn.fetch(FetchRequest(symbol="BTC/USDT", limit=50))
    assert len(result) == 50
    assert result.source_mode == "synthetic"
