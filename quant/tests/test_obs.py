"""WP-8.2 — observability: local experiment logging + Prometheus-text metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantos.obs import Counter, ExperimentLogger, Gauge, MetricsRegistry


class TestExperimentLogger:
    def test_writes_a_local_run_record(self, tmp_path: Path) -> None:
        logger = ExperimentLogger(tracking_dir=tmp_path / "mlruns")
        assert logger.backend == "local-json"  # mlflow absent here (I6)
        run_id = logger.log_run(
            "lab-batch-1",
            params={"seed": 42, "n_specs": 100},
            metrics={"best_fitness": 1.7, "pbo": 0.14},
            tags={"regime": "TREND_UP"},
        )
        files = list((tmp_path / "mlruns" / "quantos").glob("*.json"))
        assert len(files) == 1
        record = json.loads(files[0].read_text())
        assert record["run_id"] == run_id
        assert record["metrics"]["best_fitness"] == 1.7

    def test_run_id_is_deterministic(self, tmp_path: Path) -> None:
        logger = ExperimentLogger(tracking_dir=tmp_path / "a")
        other = ExperimentLogger(tracking_dir=tmp_path / "b")
        payload = {"params": {"seed": 1}, "metrics": {"x": 2.0}}
        assert logger.log_run("r", **payload) == other.log_run("r", **payload)  # I8

    def test_runs_listing(self, tmp_path: Path) -> None:
        logger = ExperimentLogger(tracking_dir=tmp_path)
        logger.log_run("a", metrics={"x": 1.0})
        logger.log_run("b", metrics={"x": 2.0})
        assert {r["name"] for r in logger.runs()} == {"a", "b"}


class TestMetrics:
    def test_counter_and_gauge(self) -> None:
        registry = MetricsRegistry()
        trades = registry.counter("quantos_paper_trades_total", "paper trades placed")
        trades.inc(symbol="BTC/USDT")
        trades.inc(2.0, symbol="BTC/USDT")
        lag = registry.gauge("quantos_connector_lag_seconds", "ingestion lag")
        lag.set(12.5, connector="market")
        assert trades.value(symbol="BTC/USDT") == 3.0
        assert lag.value(connector="market") == 12.5

    def test_counters_only_go_up(self) -> None:
        with pytest.raises(ValueError):
            Counter("c").inc(-1.0)

    def test_prometheus_text_exposition(self) -> None:
        registry = MetricsRegistry()
        registry.counter("t_total", "help text").inc(symbol="BTC/USDT")
        registry.gauge("g", "a gauge").set(1.5)
        text = registry.render()
        assert "# TYPE t_total counter" in text
        assert 't_total{symbol="BTC/USDT"} 1.0' in text
        assert "# TYPE g gauge" in text and "\ng 1.5" in text

    def test_create_or_get_and_type_safety(self) -> None:
        registry = MetricsRegistry()
        assert registry.counter("x") is registry.counter("x")
        with pytest.raises(TypeError):
            registry.gauge("x")

    def test_snapshot_is_json_friendly(self) -> None:
        registry = MetricsRegistry()
        registry.counter("x").inc(kind="a")
        json.dumps(registry.as_dict())

    def test_paper_engine_can_instrument(self) -> None:
        """The intended usage: engines increment the shared default registry."""
        from quantos.obs import metrics as shared

        counter = shared.counter("quantos_test_events_total", "test events")
        before = counter.value(kind="unit")
        counter.inc(kind="unit")
        assert counter.value(kind="unit") == before + 1.0
        assert isinstance(shared.render(), str)


def test_gauge_render_without_labels() -> None:
    gauge = Gauge("plain")
    gauge.set(2.0)
    assert "plain 2.0" in gauge.render()
