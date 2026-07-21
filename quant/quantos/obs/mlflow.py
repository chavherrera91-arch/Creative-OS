"""Experiment logging — MLflow when available, plain local runs otherwise.

The :class:`ExperimentLogger` records backtest / Strategy-Lab / GA runs
(params + metrics + tags). With the ``[obs]`` extra installed it logs through
MLflow's local file backend; without it, it writes the same record as one
JSON file per run under the tracking directory — so research history is
never lost to a missing dependency (I6) and the interface is identical
either way. MLflow is imported lazily and never required by tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["ExperimentLogger"]


def _mlflow_or_none() -> Any:
    try:
        import mlflow
    except ImportError:
        return None
    return mlflow


class ExperimentLogger:
    """Log named runs with params/metrics/tags to a local tracking dir."""

    def __init__(self, tracking_dir: str | Path = "mlruns", experiment: str = "quantos") -> None:
        """
        Args:
            tracking_dir: local directory MLflow (or the fallback) writes to.
            experiment: experiment name grouping the runs.
        """
        self.tracking_dir = Path(tracking_dir)
        self.experiment = experiment
        self._mlflow = _mlflow_or_none()

    @property
    def backend(self) -> str:
        """``"mlflow"`` with the extra installed, else ``"local-json"``."""
        return "mlflow" if self._mlflow is not None else "local-json"

    def log_run(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        metrics: dict[str, float] | None = None,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Record one run; returns its id. Deterministic id offline (I8)."""
        params = dict(params or {})
        metrics = {k: float(v) for k, v in (metrics or {}).items()}
        tags = dict(tags or {})
        if self._mlflow is not None:  # pragma: no cover - needs the [obs] extra
            return self._log_mlflow(name, params, metrics, tags)
        return self._log_local(name, params, metrics, tags)

    # -- backends -------------------------------------------------------------
    def _log_mlflow(
        self, name: str, params: dict, metrics: dict, tags: dict
    ) -> str:  # pragma: no cover - needs the [obs] extra
        mlflow = self._mlflow
        mlflow.set_tracking_uri(f"file:{self.tracking_dir.resolve()}")
        mlflow.set_experiment(self.experiment)
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            mlflow.set_tags(tags)
            return str(run.info.run_id)

    def _log_local(self, name: str, params: dict, metrics: dict, tags: dict) -> str:
        record = {
            "experiment": self.experiment,
            "name": name,
            "params": params,
            "metrics": metrics,
            "tags": tags,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        run_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        run_dir = self.tracking_dir / self.experiment
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"{run_id}.json").write_text(
            json.dumps({**record, "run_id": run_id}, sort_keys=True, indent=2, default=str)
        )
        return run_id

    def runs(self) -> list[dict[str, Any]]:
        """Every locally recorded run (fallback backend), id-ordered (I8)."""
        run_dir = self.tracking_dir / self.experiment
        if not run_dir.exists():
            return []
        return [json.loads(path.read_text()) for path in sorted(run_dir.glob("*.json"))]
