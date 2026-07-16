import pandas as pd
import pytest

from quantos.data.connectors import (
    Connector,
    ConnectorMetadata,
    ConnectorRegistry,
    FetchRequest,
    FetchResult,
    register,
    registry,
)


def _dummy_rows(req: FetchRequest) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=req.limit, freq="1h", tz="UTC")
    return pd.DataFrame({
        "symbol": [req.symbol] * req.limit,
        "event_time": times,
        "value": range(req.limit),
    })


class DummyConnector(Connector):
    metadata = ConnectorMetadata(
        name="dummy", category="test", schema_name="dummy", cadence_seconds=3600
    )

    def fetch(self, req: FetchRequest) -> FetchResult:
        return self.synthetic(req)

    def synthetic(self, req: FetchRequest) -> FetchResult:
        return FetchResult(self._stamp_ingested(_dummy_rows(req)), 1, "synthetic")


def test_register_and_get_on_isolated_registry():
    reg = ConnectorRegistry()
    reg.register(DummyConnector())
    assert reg.get("dummy").metadata.category == "test"
    assert "dummy" in reg.names()
    assert len(reg.by_category("test")) == 1


def test_duplicate_registration_raises():
    reg = ConnectorRegistry()
    reg.register(DummyConnector())
    with pytest.raises(ValueError):
        reg.register(DummyConnector())


def test_unknown_connector_raises():
    with pytest.raises(KeyError):
        ConnectorRegistry().get("nope")


def test_add_connector_with_zero_core_edits():
    """The headline acceptance criterion: a brand-new @register-ed connector
    flows through the default registry without touching any core module."""
    before = set(registry.names())
    try:
        @register
        class PluginConnector(Connector):
            metadata = ConnectorMetadata(
                name="plugin_demo", category="test",
                schema_name="plugin_demo", cadence_seconds=60,
            )

            def fetch(self, req):
                return self.synthetic(req)

            def synthetic(self, req):
                return FetchResult(self._stamp_ingested(_dummy_rows(req)), 1, "synthetic")

        assert "plugin_demo" in registry.names()
        conn = registry.get("plugin_demo")
        result = conn.fetch(FetchRequest(symbol="BTC", limit=5))
        assert isinstance(result, FetchResult)
        assert len(result) == 5
        assert "ingested_at" in result.rows.columns  # event_time vs ingested_at (I2)
    finally:
        # keep the global registry clean for other tests
        registry._connectors.pop("plugin_demo", None)
    assert set(registry.names()) == before


def test_healthcheck_default_probe():
    status = DummyConnector().healthcheck()
    assert status.healthy
    assert status.latency_ms is not None
