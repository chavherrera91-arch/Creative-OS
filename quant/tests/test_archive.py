"""WP-7.1 — Decision Archive: dossier + outcome round-trips, queries, replay (I8)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantos.committee.committee import default_committee
from quantos.data.models import MarketSnapshot
from quantos.data.store import DuckDBStore
from quantos.memory import DecisionArchive


def bullish_snapshot(ohlcv: pd.DataFrame) -> MarketSnapshot:
    return MarketSnapshot(
        "BTC/USDT",
        "1h",
        ohlcv,
        macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
        sentiment={"score": 0.6},
        onchain={"whale_accumulation": 0.8},
    )


def fake_record(
    symbol: str = "BTC/USDT", as_of: str = "2024-02-01T00:00:00+00:00", regime: str = "TREND_UP"
) -> dict:
    """A minimal hand-built decision dict (the archive accepts dicts too)."""
    return {
        "symbol": symbol,
        "timeframe": "1h",
        "price": 100.0,
        "direction": "LONG",
        "approved": True,
        "confidence": 0.9,
        "blocked_by_risk": False,
        "reasons": ["seed"],
        "opinions": [],
        "regime": {"label": regime},
        "strategies_considered": [],
        "run_manifest": {"seed": 42},
        "as_of": as_of,
    }


class TestRoundTrip:
    def test_decision_round_trips_and_is_idempotent(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(bullish_snapshot(uptrend_ohlcv))
        archive = DecisionArchive()
        did = archive.record(decision)
        assert archive.record(decision) == did  # same content, same id (I8)
        assert len(archive) == 1
        stored = archive.get(did)
        assert stored.decision == decision.as_dict()  # full dossier survives (I4)
        assert not stored.closed and stored.pnl is None and stored.won is None

    def test_outcome_round_trip(self) -> None:
        archive = DecisionArchive()
        did = archive.record(fake_record())
        archive.record_outcome(did, pnl=25.0, notes="took profit at resistance")
        closed = archive.get(did)
        assert closed.closed and closed.pnl == 25.0 and closed.won is True
        assert closed.outcome_notes == "took profit at resistance"
        # the dossier itself is untouched by the outcome
        assert closed.decision == fake_record()

    def test_unknown_ids_raise(self) -> None:
        archive = DecisionArchive()
        with pytest.raises(KeyError):
            archive.get("nope")
        with pytest.raises(KeyError):
            archive.record_outcome("nope", pnl=1.0)


class TestQueries:
    def build(self) -> DecisionArchive:
        archive = DecisionArchive()
        self.a = archive.record(fake_record("BTC/USDT", "2024-01-10T00:00:00+00:00", "TREND_UP"))
        self.b = archive.record(fake_record("ETH/USDT", "2024-02-10T00:00:00+00:00", "RANGE"))
        self.c = archive.record(fake_record("BTC/USDT", "2024-03-10T00:00:00+00:00", "CRISIS"))
        archive.record_outcome(self.c, pnl=-5.0)
        return archive

    def test_by_symbol(self) -> None:
        archive = self.build()
        assert {r.symbol for r in archive.query(symbol="BTC/USDT")} == {"BTC/USDT"}
        assert len(archive.query(symbol="BTC/USDT")) == 2

    def test_by_window(self) -> None:
        archive = self.build()
        february = archive.query(start="2024-02-01", end="2024-02-28")
        assert [r.decision_id for r in february] == [self.b]

    def test_by_regime(self) -> None:
        archive = self.build()
        assert [r.decision_id for r in archive.query(regime="CRISIS")] == [self.c]

    def test_closed_corpus(self) -> None:
        archive = self.build()
        closed = archive.closed()
        assert [r.decision_id for r in closed] == [self.c]
        assert closed[0].won is False


class TestReplayAndPersistence:
    def test_manifest_supports_bitwise_replay(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """Same snapshot, fresh committee — identical dossier, identical id (I8)."""
        snapshot = bullish_snapshot(uptrend_ohlcv)
        first = default_committee().deliberate(snapshot)
        archive = DecisionArchive()
        did = archive.record(first)
        assert archive.get(did).decision.get("run_manifest")  # manifest is pinned
        replay = default_committee().deliberate(snapshot)
        assert archive.record(replay) == did
        assert len(archive) == 1

    def test_archive_survives_restart_on_disk(self, tmp_path: Path) -> None:
        root = tmp_path / "lake"
        did = DecisionArchive(DuckDBStore(root=root)).record(fake_record())
        reopened = DecisionArchive(DuckDBStore(root=root))
        assert reopened.get(did).symbol == "BTC/USDT"
        reopened.record_outcome(did, pnl=3.0)
        assert DecisionArchive(DuckDBStore(root=root)).get(did).closed
