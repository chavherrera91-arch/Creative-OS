"""WP-2.8 — FeatureStore: explicit no-look-ahead (I2) as-of reads."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.data.featurestore import FeatureStore
from quantos.data.store import DuckDBStore

T0 = pd.Timestamp("2024-01-01 00:00", tz="UTC")


def hours(n: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(hours=n)


@pytest.fixture()
def store() -> DuckDBStore:
    store = DuckDBStore()
    store.write(
        "curated",
        "prices",
        pd.DataFrame(
            {
                "symbol": ["BTC/USDT"] * 4,
                "event_time": [hours(0), hours(1), hours(2), hours(3)],
                "close": [100.0, 101.0, 102.0, 103.0],
            }
        ),
    )
    store.write(
        "curated",
        "funding",
        pd.DataFrame(
            {
                "symbol": ["BTC/USDT"] * 2,
                "event_time": [hours(0), hours(8)],
                "rate": [0.0001, 0.0009],
            }
        ),
    )
    return store


class TestAsOf:
    def test_returns_latest_value_at_or_before_at(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        values = fs.as_of("BTC/USDT", hours(2), ["prices.close"])
        assert values == {"prices.close": 102.0}

    def test_never_returns_event_time_greater_than_at(self, store: DuckDBStore) -> None:
        # The I2 guarantee, stated as the acceptance test (§7.5): a value
        # whose event_time is in the future of `at` must NEVER be served.
        fs = FeatureStore(store)
        between = hours(1) + pd.Timedelta(minutes=30)
        values = fs.as_of("BTC/USDT", between, ["prices.close", "funding.rate"])
        assert values["prices.close"] == 101.0  # hours(1), not hours(2)
        assert values["funding.rate"] == 0.0001  # hours(0), not hours(8)

    def test_before_first_observation_is_an_honest_absence(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        values = fs.as_of("BTC/USDT", T0 - pd.Timedelta(hours=1), ["prices.close"])
        assert values == {}  # absent, never fabricated (I3 in spirit)

    def test_unknown_symbol_or_table_is_absent(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        assert fs.as_of("ETH/USDT", hours(2), ["prices.close"]) == {}
        assert fs.as_of("BTC/USDT", hours(2), ["nope.close"]) == {}

    def test_malformed_feature_name_rejected(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        with pytest.raises(ValueError):
            fs.as_of("BTC/USDT", hours(2), ["close"])


class TestFrame:
    def test_grid_values_are_backward_asof(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        frame = fs.frame("BTC/USDT", T0, hours(10), ["prices.close", "funding.rate"])
        # at hour 5 the last price is hour 3's close; funding still hour 0's
        assert frame.loc[hours(5), "prices.close"] == 103.0
        assert frame.loc[hours(5), "funding.rate"] == 0.0001
        # funding flips only once its hour-8 event has happened
        assert frame.loc[hours(8), "funding.rate"] == 0.0009
        assert frame.loc[hours(7), "funding.rate"] == 0.0001

    def test_no_value_before_first_event(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        frame = fs.frame(
            "BTC/USDT", T0 - pd.Timedelta(hours=2), hours(1), ["prices.close"]
        )
        assert frame.loc[T0 - pd.Timedelta(hours=1), "prices.close"] != frame.loc[
            T0, "prices.close"
        ]
        assert pd.isna(frame.loc[T0 - pd.Timedelta(hours=1), "prices.close"])

    def test_missing_column_yields_nan_not_error(self, store: DuckDBStore) -> None:
        fs = FeatureStore(store)
        frame = fs.frame("BTC/USDT", T0, hours(2), ["prices.nope"])
        assert frame["prices.nope"].isna().all()
