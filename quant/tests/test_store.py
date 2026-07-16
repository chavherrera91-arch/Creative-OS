import pandas as pd
import pytest

from quantos.data.store import DuckDBStore, Store, get_store


def _frame(times, symbol="BTC", closes=None):
    closes = closes if closes is not None else [float(i) for i in range(len(times))]
    return pd.DataFrame({
        "symbol": [symbol] * len(times),
        "event_time": pd.to_datetime(times, utc=True),
        "ingested_at": pd.Timestamp.now("UTC"),
        "close": closes,
    })


@pytest.fixture(params=["memory", "disk"])
def store(request, tmp_path):
    if request.param == "memory":
        return DuckDBStore(root=None)
    return DuckDBStore(root=tmp_path / "lake")


def test_store_satisfies_protocol(store):
    assert isinstance(store, Store)


def test_write_read_roundtrip_is_lossless(store):
    df = _frame(["2024-01-01", "2024-01-02", "2024-01-03"])
    store.write("raw", "market", df)
    out = store.read("raw", "market")
    assert len(out) == 3
    assert list(out["close"]) == [0.0, 1.0, 2.0]
    # tz-aware timestamps survive the round-trip
    assert out["event_time"].dt.tz is not None


def test_upsert_is_idempotent(store):
    df = _frame(["2024-01-01", "2024-01-02"])
    keys = ["symbol", "event_time"]
    n1 = store.upsert("curated", "market", df, keys)
    n2 = store.upsert("curated", "market", df, keys)  # same rows again
    assert n1 == n2 == 2
    assert len(store.read("curated", "market")) == 2


def test_upsert_replaces_on_key(store):
    keys = ["symbol", "event_time"]
    store.upsert("curated", "m", _frame(["2024-01-01"], closes=[10.0]), keys)
    store.upsert("curated", "m", _frame(["2024-01-01"], closes=[99.0]), keys)
    out = store.read("curated", "m")
    assert len(out) == 1
    assert out["close"].iloc[0] == 99.0  # last write wins


def test_read_filters_by_symbol_and_window(store):
    store.write("raw", "m", _frame(["2024-01-01", "2024-01-05"], symbol="BTC"))
    store.write("raw", "m", _frame(["2024-01-02"], symbol="ETH"))
    assert set(store.read("raw", "m", symbol="ETH")["symbol"]) == {"ETH"}
    windowed = store.read("raw", "m", symbol="BTC", start="2024-01-03", end="2024-01-10")
    assert len(windowed) == 1


def test_tables_listing(store):
    store.write("raw", "alpha", _frame(["2024-01-01"]))
    store.write("raw", "beta", _frame(["2024-01-01"]))
    assert store.tables("raw") == ["alpha", "beta"]
    assert store.tables("curated") == []


def test_unknown_tier_raises(store):
    with pytest.raises(ValueError):
        store.write("nonsense", "m", _frame(["2024-01-01"]))


def test_read_missing_table_returns_empty(store):
    assert store.read("features", "absent").empty


def test_get_store_default_is_duckdb():
    assert isinstance(get_store(), DuckDBStore)
