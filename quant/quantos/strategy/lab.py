"""Strategy Lab (module 5, WP-5.3): auto-backtest, honest ranking, cull.

``StrategyLab.run(specs, ohlcv)`` pushes every candidate through the M1
backtest engine (M3 cost model pluggable), splits the run into an in-sample
and a held-out out-of-sample window, and ranks by a fitness that **folds in
the M3 anti-overfitting statistics** (invariant I9):

- the OOS Sharpe is multiplied by the **Deflated Sharpe Ratio** computed at
  ``n_trials = len(candidates)`` — the more strategies the lab tried, the
  higher the bar, so a data-mined/lucky spec's apparent edge is deflated
  toward zero and cannot top the ranking on in-sample luck;
- negative OOS Sharpe passes through *undeflated* (bad news is never
  discounted) and the maximum drawdown is penalised;
- the batch-level **PBO** (probability of backtest overfitting, CSCV) is
  computed across all candidates and recorded with the run.

The weak are **culled** (only the top-k with an acceptable DSR survive) and
every record — including the **regime the batch was tested under** — is
persisted to the ``Store`` as raw material for the M7 Meta-Learner. Ranking
is deterministic offline (I6/I8); optional MLflow logging is lazy and never
required.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.backtest.engine import backtest
from quantos.backtest.metrics import HOURS_PER_YEAR, summarize
from quantos.backtest.validation import deflated_sharpe_from_returns, pbo
from quantos.data.models import MarketSnapshot
from quantos.data.store.base import Store
from quantos.execution.costs import CostModel
from quantos.regime.classifier import RuleRegimeClassifier
from quantos.strategy.base import IndicatorStrategy, SignalStrategy, Strategy, StrategySpec

__all__ = ["LabRecord", "LabResult", "StrategyLab"]


@dataclass
class LabRecord:
    """One candidate's full lab dossier (auditable, I4).

    Attributes:
        rank: 1-based position in the fitness ranking.
        spec: the strategy description that was tested (pinned, I8).
        fitness: DSR-deflated, drawdown-penalised OOS score (I9).
        survived: True when the record cleared the cull.
        tested_regime: regime label of the data the batch ran on.
        is_metrics: in-sample metrics (reported, never ranked on).
        oos_metrics: held-out out-of-sample metrics.
        validation: the Deflated Sharpe report over the OOS returns (I9).
        n_trades: number of position changes over the full sample.
    """

    rank: int
    spec: StrategySpec
    fitness: float
    survived: bool
    tested_regime: str
    is_metrics: dict[str, float] = field(default_factory=dict)
    oos_metrics: dict[str, float] = field(default_factory=dict)
    validation: dict[str, float] = field(default_factory=dict)
    n_trades: int = 0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "rank": self.rank,
            "spec": self.spec.as_dict(),
            "spec_hash": self.spec.spec_hash(),
            "fitness": self.fitness,
            "survived": self.survived,
            "tested_regime": self.tested_regime,
            "is_metrics": dict(self.is_metrics),
            "oos_metrics": dict(self.oos_metrics),
            "validation": dict(self.validation),
            "n_trades": self.n_trades,
        }


@dataclass
class LabResult:
    """A full lab run: ranked records plus the batch-level statistics.

    ``pbo`` is the CSCV Probability of Backtest Overfitting across the whole
    candidate batch (NaN when fewer than two candidates ran) — the honesty
    label attached to the run itself (I9).
    """

    run_id: str
    records: list[LabRecord] = field(default_factory=list)
    pbo: float = float("nan")
    tested_regime: str = ""
    n_trials: int = 0

    @property
    def survivors(self) -> list[StrategySpec]:
        """The specs that cleared the cull, best first."""
        return [r.spec for r in self.records if r.survived]

    def record_for(self, spec: StrategySpec) -> LabRecord:
        """Fetch the record of a specific spec.

        Raises:
            KeyError: when the spec was not part of this run.
        """
        wanted = spec.spec_hash()
        for record in self.records:
            if record.spec.spec_hash() == wanted:
                return record
        raise KeyError(f"spec {spec.key} was not tested in run {self.run_id}")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "run_id": self.run_id,
            "records": [r.as_dict() for r in self.records],
            "pbo": self.pbo,
            "tested_regime": self.tested_regime,
            "n_trials": self.n_trials,
        }


class StrategyLab:
    """Backtest, rank honestly, cull, persist (the M5 funnel front-end).

    Deterministic offline: the ranking is a pure function of the candidates
    and the data (I8); ties break on the spec hash. Persistence goes to the
    tiered :class:`Store` (``features`` tier) so the M7 Meta-Learner can
    query ``(family, tested_regime) -> validated stats`` later.
    """

    def __init__(
        self,
        store: Store | None = None,
        top_k: int = 10,
        oos_fraction: float = 0.4,
        dd_penalty: float = 0.5,
        min_dsr: float = 0.0,
        fee_bps: float = 10.0,
        slippage_bps: float = 5.0,
        periods_per_year: float = HOURS_PER_YEAR,
        cost_model: CostModel | None = None,
        symbol: str = "SYN/USD",
        timeframe: str = "1h",
        table: str = "strategy_lab",
        mlflow_uri: str | None = None,
    ) -> None:
        """
        Args:
            store: optional tiered store; when given, every run is persisted.
            top_k: how many ranked candidates survive the cull.
            oos_fraction: trailing fraction of bars held out of sample.
            dd_penalty: weight of the max-drawdown penalty in the fitness.
            min_dsr: minimum Deflated Sharpe a survivor must clear (I9 gate).
            fee_bps: flat fee per unit of turnover (when no cost model).
            slippage_bps: flat slippage per unit turnover (when no cost model).
            periods_per_year: annualisation factor for metrics.
            cost_model: optional M3 cost model routed through the backtest.
            symbol: label for snapshots/persisted rows.
            timeframe: label for snapshots/persisted rows.
            table: store table name (``features`` tier).
            mlflow_uri: optional MLflow tracking URI; lazily imported and
                silently skipped when MLflow is not installed (I6).
        """
        if not 0.0 < oos_fraction < 1.0:
            raise ValueError(f"oos_fraction must be in (0, 1), got {oos_fraction}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        self.store = store
        self.top_k = top_k
        self.oos_fraction = oos_fraction
        self.dd_penalty = dd_penalty
        self.min_dsr = min_dsr
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.periods_per_year = periods_per_year
        self.cost_model = cost_model
        self.symbol = symbol
        self.timeframe = timeframe
        self.table = table
        self.mlflow_uri = mlflow_uri
        self._classifier = RuleRegimeClassifier()

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _as_strategy(candidate: StrategySpec | Strategy) -> Strategy:
        """Resolve a candidate into a runnable strategy carrying its spec."""
        if isinstance(candidate, StrategySpec):
            return IndicatorStrategy(candidate)
        if isinstance(candidate, SignalStrategy) and isinstance(
            getattr(candidate, "spec", None), StrategySpec
        ):
            return candidate  # already a Strategy (I7): any implementation plugs in
        raise TypeError(
            f"cannot test a {type(candidate).__name__}: expected a StrategySpec "
            "or a Strategy (signals + spec)"
        )

    def _run_id(self, hashes: Sequence[str], ohlcv: pd.DataFrame) -> str:
        """Deterministic run identity from the batch + data window (I8)."""
        payload = "|".join(
            [*sorted(hashes), str(ohlcv.index[0]), str(ohlcv.index[-1]), str(len(ohlcv))]
        )
        return "lab-" + hashlib.sha256(payload.encode()).hexdigest()[:12]

    def _fitness(self, oos_metrics: dict[str, float], dsr: float) -> float:
        """DSR-deflated Sharpe with a drawdown penalty (I9).

        A positive OOS Sharpe is multiplied by the DSR — the probability the
        edge is real given how many candidates were tried — so a lucky spec
        collapses toward 0. A negative Sharpe is never discounted, and the
        (negative) max drawdown subtracts ``dd_penalty`` times its size.
        """
        sharpe = oos_metrics["sharpe"]
        deflated = dsr * max(sharpe, 0.0) + min(sharpe, 0.0)
        return deflated + self.dd_penalty * oos_metrics["max_drawdown"]

    # -- the lab run -------------------------------------------------------

    def run(
        self,
        specs: Sequence[StrategySpec | Strategy],
        ohlcv: pd.DataFrame,
        run_id: str | None = None,
    ) -> LabResult:
        """Backtest, rank, cull and persist a batch of candidates.

        Args:
            specs: strategy specs (compiled in-lab) and/or ready
                :class:`Strategy` objects.
            ohlcv: bar history; the trailing ``oos_fraction`` is the held-out
                window every ranking statistic is computed on.
            run_id: optional explicit run identity; a deterministic hash of
                the batch + data window when omitted (I8 — never a clock).

        Returns:
            A :class:`LabResult` with ranked records, batch PBO and the
            tested regime.

        Raises:
            ValueError: on an empty batch or too short a sample.
        """
        if not specs:
            raise ValueError("StrategyLab.run needs at least one candidate")
        strategies = [self._as_strategy(c) for c in specs]
        n = len(ohlcv)
        split = n - int(n * self.oos_fraction)
        if split < 2 or n - split < 2:
            raise ValueError(
                f"sample of {n} bars is too short for oos_fraction={self.oos_fraction}"
            )

        snapshot = MarketSnapshot(symbol=self.symbol, timeframe=self.timeframe, ohlcv=ohlcv)
        tested_regime = self._classifier.classify(snapshot).label
        n_trials = len(strategies)

        rows: list[dict[str, Any]] = []
        is_panel: dict[str, pd.Series] = {}
        oos_panel: dict[str, pd.Series] = {}
        for strategy in strategies:
            spec = strategy.spec
            result = backtest(
                ohlcv,
                strategy.signals(ohlcv),
                fee_bps=self.fee_bps,
                slippage_bps=self.slippage_bps,
                periods_per_year=self.periods_per_year,
                cost_model=self.cost_model,
            )
            is_returns = result.returns.iloc[:split]
            oos_returns = result.returns.iloc[split:]
            validation = deflated_sharpe_from_returns(oos_returns, n_trials=n_trials)
            oos_metrics = summarize(oos_returns, self.periods_per_year)
            chash = spec.spec_hash()
            is_panel[chash] = is_returns
            oos_panel[chash] = oos_returns
            rows.append(
                {
                    "spec": spec,
                    "fitness": self._fitness(oos_metrics, validation["deflated_sharpe"]),
                    "is_metrics": summarize(is_returns, self.periods_per_year),
                    "oos_metrics": oos_metrics,
                    "validation": validation,
                    "n_trades": result.n_trades,
                }
            )

        batch_pbo = float("nan")
        if n_trials >= 2:
            columns = sorted(is_panel)
            batch_pbo = pbo(
                pd.DataFrame({c: is_panel[c] for c in columns}),
                pd.DataFrame({c: oos_panel[c] for c in columns}),
            )

        # Deterministic ranking: fitness desc, spec hash as the tie-break (I8).
        rows.sort(key=lambda r: (-r["fitness"], r["spec"].spec_hash()))
        records = [
            LabRecord(
                rank=i + 1,
                spec=row["spec"],
                fitness=float(row["fitness"]),
                survived=(
                    i < self.top_k and row["validation"]["deflated_sharpe"] >= self.min_dsr
                ),
                tested_regime=tested_regime,
                is_metrics=row["is_metrics"],
                oos_metrics=row["oos_metrics"],
                validation=row["validation"],
                n_trades=int(row["n_trades"]),
            )
            for i, row in enumerate(rows)
        ]
        result_ = LabResult(
            run_id=run_id or self._run_id([r.spec.spec_hash() for r in records], ohlcv),
            records=records,
            pbo=batch_pbo,
            tested_regime=tested_regime,
            n_trials=n_trials,
        )
        self._persist(result_, ohlcv)
        self._log_mlflow(result_)
        return result_

    # -- persistence -------------------------------------------------------

    def _persist(self, result: LabResult, ohlcv: pd.DataFrame) -> None:
        """Upsert the run's records into the store (idempotent on re-run)."""
        if self.store is None:
            return
        frame = pd.DataFrame(
            [
                {
                    "run_id": result.run_id,
                    "spec_hash": r.spec.spec_hash(),
                    "symbol": self.symbol,
                    "event_time": ohlcv.index[-1],
                    "name": r.spec.name,
                    "version": r.spec.version,
                    "family": r.spec.family,
                    "target_regimes": json.dumps(list(r.spec.target_regimes)),
                    "tested_regime": r.tested_regime,
                    "rank": r.rank,
                    "fitness": r.fitness,
                    "survived": r.survived,
                    "oos_sharpe": r.oos_metrics.get("sharpe", 0.0),
                    "is_sharpe": r.is_metrics.get("sharpe", 0.0),
                    "oos_max_drawdown": r.oos_metrics.get("max_drawdown", 0.0),
                    "deflated_sharpe": r.validation.get("deflated_sharpe", 0.0),
                    "pbo": result.pbo,
                    "n_trades": r.n_trades,
                    "spec_json": r.spec.canonical(),
                }
                for r in result.records
            ]
        )
        self.store.upsert("features", self.table, frame, keys=["run_id", "spec_hash"])

    def _log_mlflow(self, result: LabResult) -> None:
        """Optionally log the run to MLflow — lazy, never required (I6)."""
        if self.mlflow_uri is None:
            return
        try:
            import mlflow  # noqa: PLC0415 — optional accelerator, lazy by design
        except ImportError:
            return  # research path must not depend on optional tooling
        mlflow.set_tracking_uri(self.mlflow_uri)
        with mlflow.start_run(run_name=result.run_id):
            mlflow.log_metric("pbo", result.pbo)
            for record in result.records:
                mlflow.log_metric(f"fitness_rank_{record.rank}", record.fitness)
