"""WP-2.2 — tiered store: round-trips, idempotent upsert, lazy Timescale."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantos.data.store import TIERS, DuckDBStore, Store, TimescaleStore


def make_rows(n: int = 5, symbol: str = "BTC/USDT", offset: int = 0) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n + offset, freq="1h", tz="UTC")[offset:]
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "event_time": times,
            "close": [100.0 + i for i in range(n)],
        }
    )


@pytest.fixture(params=["memory", "disk"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> DuckDBStore:
    root = None if request.param == "memory" else tmp_path / "lake"
    return DuckDBStore(root=root)


class TestDuckDBStore:
    def test_satisfies_store_protocol(self, store: DuckDBStore) -> None:
        assert isinstance(store, Store)

    def test_round_trip_per_tier(self, store: DuckDBStore) -> None:
        rows = make_rows()
        for tier in TIERS:
            written = store.write(tier, "market", rows)
            assert written == len(rows)
            back = store.read(tier, "market")
            pd.testing.assert_frame_equal(back, rows.reset_index(drop=True))
            assert store.tables(tier) == ["market"]

    def test_unknown_tier_rejected(self, store: DuckDBStore) -> None:
        with pytest.raises(ValueError):
            store.write("hot", "market", make_rows())

    def test_upsert_is_idempotent(self, store: DuckDBStore) -> None:
        rows = make_rows()
        added = store.upsert("curated", "market", rows, keys=["symbol", "event_time"])
        assert added == len(rows)
        again = store.upsert("curated", "market", rows, keys=["symbol", "event_time"])
        assert again == 0
        assert len(store.read("curated", "market")) == len(rows)

    def test_upsert_replaces_on_key_and_appends_new(self, store: DuckDBStore) -> None:
        store.upsert("curated", "market", make_rows(5), keys=["symbol", "event_time"])
        overlap = make_rows(5, offset=3)  # 2 overlapping keys, 3 new
        overlap["close"] = overlap["close"] + 1000.0
        added = store.upsert("curated", "market", overlap, keys=["symbol", "event_time"])
        assert added == 3
        table = store.read("curated", "market")
        assert len(table) == 8
        # overlapping keys carry the replacement values (keep last)
        replaced = table[table["event_time"].isin(overlap["event_time"])]
        assert (replaced["close"] > 999.0).all()

    def test_read_filters_symbol_and_window(self, store: DuckDBStore) -> None:
        store.write("curated", "market", make_rows(5, symbol="BTC/USDT"))
        store.write("curated", "market", make_rows(5, symbol="ETH/USDT"))
        btc = store.read("curated", "market", symbol="BTC/USDT")
        assert set(btc["symbol"]) == {"BTC/USDT"}
        window = store.read(
            "curated",
            "market",
            symbol="BTC/USDT",
            start="2024-01-01 01:00+00:00",
            end="2024-01-01 03:00+00:00",
        )
        assert len(window) == 3

    def test_disk_store_persists_across_instances(self, tmp_path: Path) -> None:
        root = tmp_path / "lake"
        DuckDBStore(root=root).write("curated", "market", make_rows())
        reopened = DuckDBStore(root=root)
        assert len(reopened.read("curated", "market")) == 5

    def test_query_via_duckdb(self, store: DuckDBStore) -> None:
        pytest.importorskip("duckdb")
        store.write("curated", "market", make_rows())
        out = store.query("SELECT COUNT(*) AS n FROM market")
        assert int(out["n"].iloc[0]) == 5


class TestTimescaleStore:
    def test_imports_and_instantiates_without_driver(self) -> None:
        # The module must import and the class construct with no psycopg and
        # no DSN — the driver is lazy and the DSN comes from env only (I6).
        st = TimescaleStore()
        assert st.dsn is None or isinstance(st.dsn, str)

    def test_operations_fail_gracefully_offline(self) -> None:
        st = TimescaleStore(dsn=None)
        with pytest.raises(RuntimeError):
            st.write("curated", "market", make_rows())

    def test_no_hardcoded_dsn(self) -> None:
        source = Path(TimescaleStore.__module__.replace(".", "/") + ".py")
        text = (Path(__file__).parents[1] / source).read_text()
        assert "postgres://" not in text and "postgresql://" not in text
