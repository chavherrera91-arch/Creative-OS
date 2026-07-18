"""WP-2.9 — CLI lake commands + docker-compose hygiene."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quantos.cli import main
from quantos.data.store import DuckDBStore

SYMBOL = "BTC/USDT"


def run_cli(*argv: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


class TestIngestCommand:
    def test_ingest_runs_offline_against_duckdb_store(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        code, out = run_cli(
            "ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys
        )
        assert code == 0
        for name in ("market", "derivatives", "onchain", "macro", "sentiment", "news"):
            assert name in out
        assert "FAILED" not in out
        store = DuckDBStore(root=root)
        assert len(store.read("curated", "market", symbol=SYMBOL)) > 0

    def test_second_ingest_is_idempotent_across_processes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        run_cli("ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys)
        counts = {
            t: len(DuckDBStore(root=root).read("curated", t))
            for t in DuckDBStore(root=root).tables("curated")
        }
        run_cli("ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys)
        again = {
            t: len(DuckDBStore(root=root).read("curated", t))
            for t in DuckDBStore(root=root).tables("curated")
        }
        assert counts == again


class TestDecideFromLake:
    def test_zero_abstention_decision_from_lake(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        run_cli("ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys)
        code, out = run_cli(
            "decide",
            "--symbol",
            SYMBOL,
            "--synthetic",
            "--from-lake",
            "--lake-root",
            root,
            capsys=capsys,
        )
        assert code == 0
        assert "data source: lake" in out
        assert "5 active / 0 abstained" in out  # every analyst participated

    def test_decide_from_empty_lake_ingests_first(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        code, out = run_cli(
            "decide",
            "--symbol",
            SYMBOL,
            "--synthetic",
            "--from-lake",
            "--lake-root",
            root,
            capsys=capsys,
        )
        assert code == 0
        assert "ingesting first" in out
        assert "5 active / 0 abstained" in out


class TestCatalogAndHealthCommands:
    def test_catalog_lists_ingested_datasets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        run_cli("ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys)
        code, out = run_cli("catalog", "--lake-root", root, capsys=capsys)
        assert code == 0
        assert '"dataset": "market"' in out
        assert '"schema_version": 1' in out

    def test_health_reports_every_connector(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = str(tmp_path / "lake")
        run_cli("ingest", "--symbol", SYMBOL, "--synthetic", "--lake-root", root, capsys=capsys)
        code, out = run_cli("health", "--lake-root", root, capsys=capsys)
        assert code == 0
        for name in ("market", "sentiment", "news"):
            assert f'"{name}"' in out
        assert '"success_rate"' in out


class TestDockerCompose:
    COMPOSE = Path(__file__).parents[1] / "docker-compose.yml"

    def test_compose_parses_and_declares_services(self) -> None:
        config = yaml.safe_load(self.COMPOSE.read_text())
        assert set(config["services"]) == {"timescaledb", "redis", "dashboard"}
        assert "timescale-data" in config["volumes"]

    def test_no_secrets_committed(self) -> None:
        text = self.COMPOSE.read_text()
        # credentials only via env interpolation with obvious local defaults
        assert "${QUANTOS_DB_PASSWORD" in text
        for marker in ("sk-", "AKIA", "BEGIN PRIVATE KEY", "api_key:", "token:"):
            assert marker not in text
