"""WP-8.1 — dashboard smoke: panels build from a seeded store, no UI needed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from quantos.backtest.engine import backtest
from quantos.committee.calibration import ConfidenceCalibrator
from quantos.committee.committee import default_committee
from quantos.dashboard.panels import build_dashboard_data, equity_panel
from quantos.data.models import MarketSnapshot
from quantos.data.store import DuckDBStore
from quantos.memory import DecisionArchive
from quantos.paper.broker import PaperBroker
from tests.conftest import make_ohlcv
from tests.test_archive import fake_record
from tests.test_calibration import archive_with


def seeded_world() -> dict:
    """A small end-to-end fixture: store + archive + backtest + broker + decision."""
    ohlcv = make_ohlcv(n=200, seed=7, drift=0.003, vol=0.005)
    store = DuckDBStore()
    store.upsert(
        "curated",
        "news",
        pd.DataFrame(
            {
                "symbol": ["BTC/USDT"] * 2,
                "event_time": pd.date_range("2024-01-01", periods=2, freq="1h", tz="UTC"),
                "headline": ["ETF flows accelerate", "CPI print cooler than expected"],
                "tag": ["flows", "macro"],
                "sentiment": [0.4, 0.2],
            }
        ),
        keys=["symbol", "event_time"],
    )
    archive = DecisionArchive()
    did = archive.record(fake_record())
    archive.record_outcome(did, pnl=5.0)

    broker = PaperBroker(cash=10_000.0)
    broker.submit("BTC/USDT", "buy", qty=0.1, price=100.0)

    decision = default_committee().deliberate(MarketSnapshot("BTC/USDT", "1h", ohlcv))
    result = backtest(ohlcv, pd.Series(1.0, index=ohlcv.index))
    calibrator = ConfidenceCalibrator().fit(archive_with(0.9, wins=12, losses=8))
    return {
        "store": store,
        "archive": archive,
        "broker": broker,
        "decision": decision,
        "result": result,
        "calibrator": calibrator,
    }


class TestPanels:
    def test_full_dashboard_data_builds_offline(self) -> None:
        world = seeded_world()
        data = build_dashboard_data(
            world["store"],
            world["archive"],
            backtest=world["result"],
            broker=world["broker"],
            decision=world["decision"],
            calibrator=world["calibrator"],
        )
        assert data["metrics"]["n_trades"] >= 0
        assert data["equity"]["final_equity"] > 0
        assert data["equity"]["max_drawdown"] <= 0
        assert data["positions"]["open_positions"][0]["symbol"] == "BTC/USDT"
        assert "DECISION" in data["decision"]["narrative"]  # the full narrative rides along
        assert data["regimes"]["rows"][0]["regime"] == "TREND_UP"
        assert len(data["news"]["rows"]) == 2
        assert data["reliability"]["fitted"] is True

    def test_equity_and_drawdown_are_separate_single_series(self) -> None:
        """dataviz: two charts, one series each — never a dual axis."""
        world = seeded_world()
        panel = equity_panel(world["result"])
        assert list(panel["equity"].columns) == ["equity"]
        assert list(panel["drawdown"].columns) == ["drawdown"]

    def test_panel_data_is_json_friendly(self) -> None:
        world = seeded_world()
        data = build_dashboard_data(world["store"], world["archive"])
        json.dumps(data, default=str)

    def test_empty_world_still_builds(self) -> None:
        data = build_dashboard_data(DuckDBStore(), DecisionArchive())
        assert data["news"]["rows"] == [] and data["lab"]["rows"] == []


class TestAppImport:
    def test_app_imports_without_streamlit(self) -> None:
        assert "streamlit" not in sys.modules
        import quantos.dashboard.app  # noqa: F401 — must not require the extra (I6)

        assert "streamlit" not in sys.modules

    def test_main_raises_helpfully_without_the_extra(self) -> None:
        from quantos.dashboard.app import _require_streamlit

        with pytest.raises(ImportError, match=r"\[dashboard\]"):
            _require_streamlit()


class TestLiveData:
    def test_build_live_data_runs_offline(self) -> None:
        """The app works the moment it opens — a full run, no lake needed (I6)."""
        from quantos.dashboard.demo import build_live_data

        data = build_live_data("ETF_RALLY", seed=7)
        assert data["scenario"] == "ETF_RALLY"
        assert data["metrics"]["n_trades"] >= 0
        assert 0.0 <= data["metrics"]["deflated_sharpe"] <= 1.0  # honesty layer present (I9)
        assert "DECISION" in data["decision"]["narrative"]
        assert data["regimes"]  # a regime breakdown was built
        assert data["equity"]["final_equity"] > 0

    def test_build_live_data_is_deterministic(self) -> None:
        from quantos.dashboard.demo import build_live_data

        a = build_live_data("ETF_RALLY", seed=7)
        b = build_live_data("ETF_RALLY", seed=7)
        assert a["metrics"] == b["metrics"]  # pure function of (scenario, seed) (I8)

    def test_strategy_lab_keeps_and_discards(self) -> None:
        """The research funnel: many tested, the good kept, the rest dropped (I9)."""
        from quantos.dashboard.demo import load_lab_ohlcv, run_strategy_lab

        ohlcv, label = load_lab_ohlcv("demo", "ETF_RALLY", "BTC/USDT", seed=7)
        assert "demo" in label.lower()
        lab = run_strategy_lab(ohlcv, "BTC/USDT", seed=7, n_candidates=30, top_k=8)
        assert lab["probadas"] == 30
        assert 0 < lab["guardadas"] < 30  # some kept, some discarded
        kept = [r for r in lab["rows"] if r["guardada"]]
        dropped = [r for r in lab["rows"] if not r["guardada"]]
        assert kept and dropped
        assert all("Guardada" in r["veredicto"] for r in kept)
        assert all("Descartada" in r["veredicto"] for r in dropped)


class TestLauncher:
    def test_command_targets_streamlit_and_the_app(self) -> None:
        from quantos.dashboard.launch import build_command

        command = build_command(["--server.headless", "true"])
        assert command[1:4] == ["-m", "streamlit", "run"]
        assert command[4].endswith("app.py")
        assert command[-2:] == ["--server.headless", "true"]

    def test_main_uses_the_injected_runner(self) -> None:
        from quantos.dashboard.launch import main

        seen: dict = {}
        code = main(argv=[], runner=lambda cmd: seen.setdefault("cmd", cmd) and 0 or 0)
        assert code == 0
        assert "streamlit" in seen["cmd"]  # never spawns a real process in tests

    def test_launches_with_a_console_python(self) -> None:
        from pathlib import Path

        from quantos.dashboard.launch import build_command

        exe = Path(build_command()[0]).name.lower()
        assert "pythonw" not in exe  # Streamlit needs the console python, not pythonw

    def test_log_path_is_named_for_diagnostics(self) -> None:
        from quantos.dashboard.launch import log_path

        assert log_path().name == "last-run.log"

    def test_email_prompt_is_pre_answered(self, tmp_path: Path) -> None:
        from quantos.dashboard.launch import ensure_no_email_prompt

        cred = ensure_no_email_prompt(home=tmp_path)
        assert cred.read_text() == '[general]\nemail = ""\n'  # blank email, no prompt
        # Idempotent: a second call keeps the file.
        assert ensure_no_email_prompt(home=tmp_path) == cred

    def test_theme_is_written(self, tmp_path: Path) -> None:
        from quantos.dashboard.launch import ensure_theme

        config = ensure_theme(home=tmp_path)
        text = config.read_text()
        assert "[theme]" in text and "#34D2BE" in text  # dark-teal terminal theme
