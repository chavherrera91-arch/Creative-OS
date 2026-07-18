# quantos — AI Quant Research Platform

`quantos` is an **AI quant research platform**, not a trading bot. A multi-agent
**Investment Committee** (technical / statistical / macro / sentiment / on-chain
analysts, a Risk Manager with an absolute veto, and a Chair) forms evidence-based,
fully explainable decisions; every idea is validated through a
backtest → walk-forward → Monte Carlo → paper-trading funnel; and the platform
**only paper-trades** — live execution is designed for but hard-disabled.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the master design and
[`BUILD_PLAN.md`](./BUILD_PLAN.md) for the milestone backlog.

## Non-negotiable invariants (§0)

- **I1 — No real capital.** `build_execution_engine(live=True)` raises
  `LiveExecutionDisabled`; only paper brokers accept orders.
- **I2 — No look-ahead.** Indicators are causal; backtest positions are lagged.
- **I3 — Honest abstention.** An analyst without data abstains; abstentions are
  excluded from confidence aggregation.
- **I4 — Auditability.** Every decision serialises to a complete record.
- **I5 — Risk veto is absolute.** One veto forces FLAT regardless of confidence.
- **I6 — Offline, no secrets.** Everything runs with numpy+pandas only; no keys.
- **I8 — Reproducibility.** Seeded everywhere; decisions/backtests replay identically.
- **I9 — Statistical honesty.** No single-split backtest is evidence on its own:
  walk-forward OOS results carry a Deflated Sharpe Ratio, and PBO / purged CV
  (`backtest.validation`) guard against data-mined edges.

## Install

```bash
cd quant
pip install -e .              # core: numpy + pandas only
pip install -e ".[dev]"       # + pytest, hypothesis, ruff, mypy
pip install -e ".[data]"      # + ccxt (read-only), duckdb, pyarrow (optional)
```

Configuration is via `QUANTOS_*` environment variables (see `.env.example`).
No API key is ever required: without `ccxt`/network, a seeded synthetic
generator provides deterministic market data.

## CLI

```bash
python -m quantos.cli decide     --symbol BTC/USDT --bars 400   # full explainable decision
python -m quantos.cli decide     --symbol BTC/USDT --from-lake  # snapshot from the Data Lake
python -m quantos.cli backtest   --symbol BTC/USDT --bars 400   # committee backtest + baselines
python -m quantos.cli walkforward --symbol BTC/USDT --bars 600  # out-of-sample folds
python -m quantos.cli montecarlo --symbol BTC/USDT --bars 400   # resampled risk profile
python -m quantos.cli paper      --symbol BTC/USDT --bars 400   # decide + paper execution
python -m quantos.cli ingest     --symbol BTC/USDT              # run all connectors into the lake
python -m quantos.cli catalog                                   # datasets, schemas, coverage
python -m quantos.cli health                                    # freshness / success / circuits
```

Every command runs offline and is reproducible for a fixed `--seed`.

## The Data Lake (Milestone 2 — shipped)

Every data source is a **plug-in connector** (`@register`ed, self-discovered):
market OHLCV, derivatives, on-chain, macro, sentiment and AI-tagged news. Each
has a versioned **schema** validated on write, a deterministic **synthetic**
offline mode, and an optional lazy live backend (keys via env only). Ingestion
is resilient (retry + circuit breaker), **idempotent** (primary-key upsert +
per-connector watermarks) and observable (freshness/lag/success per
connector). Storage is tiered — `raw` → `curated` → `features` — on
DuckDB/Parquet by default with optional TimescaleDB. `FeatureStore.as_of`
guarantees point-in-time reads (never a value with `event_time > at`, I2), and
`DataLake.snapshot(...)` assembles a full multi-channel `MarketSnapshot` on
which the committee deliberates with **zero abstentions**. Adding a new source
requires **zero core edits** — one new module, nothing else.

```bash
python -m quantos.cli ingest --symbol BTC/USDT      # offline: 6/6 connectors, synthetic
python -m quantos.cli decide --symbol BTC/USDT --from-lake   # 5 active / 0 abstained
```

Optional infra (never required): `docker-compose.yml` spins up TimescaleDB +
Redis + a dashboard placeholder. No secrets are committed; DSNs come from env.

## Validation rigor (Milestone 3 — shipped)

The numbers are made trustworthy end-to-end:

- **Risk limit library** (`risk/limits.py`): composable rules —
  `VolatilitySpike`, `MacroEvent`, `DailyDrawdown`, `LowLiquidity`,
  `CorrelationBreak`, `MaxPositionSize` — each returning ok/warning/veto; the
  `RiskManager` runs a configurable rule list and **one veto is still
  absolute** (I5).
- **Forward test** (`backtest/forward.py`): steps a snapshot bar-by-bar
  feeding the paper engine — the bridge between walk-forward and paper
  trading. Deterministic, no look-ahead, paper only.
- **Anti-overfitting statistics** (`backtest/validation.py`, I9):
  `deflated_sharpe` (DSR, in-house normal CDF/PPF — no scipy), `pbo`
  (Probability of Backtest Overfitting via CSCV) and
  `CombinatorialPurgedCV` (purge + embargo, leakage-proof). `walk_forward`
  attaches a DSR report to every OOS result.
- **Execution realism** (`execution/costs.py`): a pluggable `CostModel` —
  fee + size-dependent slippage + square-root market impact,
  liquidity/regime aware — routed through both the `PaperBroker` and the
  backtest. `FlatCostModel`/`ZeroCostModel` reproduce the old flat
  behaviour (back-compatible).
- **Position sizing** (`sizing/`): `VolTargetSizer`, `FractionalKellySizer`,
  `RiskParitySizer` turn a decision (direction + confidence) into a size
  **bounded by the Risk Manager's limits**; the paper executor consults the
  sizer and clamps again (I5).

## Layout

```
quantos/
├── config.py                Settings (env-driven, offline defaults)
├── data/                    M2 Data Lake
│   ├── models.py collector.py   MarketSnapshot + read-only collector
│   ├── schema/              FieldSpec/Schema, registry + migrations, validator
│   ├── store/               Store port; DuckDBStore (Parquet) · TimescaleStore (lazy)
│   ├── connectors/          plug-in sources: market, derivatives, onchain,
│   │                        macro, sentiment, news (+ @register registry)
│   ├── ingest/              RetryPolicy, CircuitBreaker, watermarks, runner,
│   │                        gap repair, 24/7 scheduler (offline run_due)
│   ├── quality/             HealthMonitor (freshness, lag, success rate)
│   ├── catalog.py           dataset inventory + lineage
│   ├── featurestore.py      point-in-time as_of reads (I2)
│   └── lake.py              DataLake facade: ingest/snapshot/catalog/health
├── features/                causal technical indicators (no look-ahead)
├── committee/               analysts, confidence model, risk veto, chair, decision
├── risk/                    composable risk limit library (M3)
├── explain/                 explain_decision / decision_report
├── backtest/                engine (lagged positions), walk-forward (+DSR), Monte
│                            Carlo, forward test, anti-overfitting statistics
│                            (DSR/PBO/CPCV), buy-and-hold + random baselines
├── paper/                   PaperBroker + per-trade dossier (TradeRecord)
├── execution/               Broker/RiskGate/ExecutionEngine ports; CostModel fills;
│                            live HARD-DISABLED
├── sizing/                  PositionSizer port + VolTarget/Kelly/RiskParity (M3)
└── cli.py                   decide | backtest | walkforward | montecarlo | paper |
                             ingest | catalog | health
```

## Tests

```bash
cd quant && python -m pytest        # offline, deterministic, fast
```

## Status

Milestones 1 (Investment Committee), 2 (Data Infrastructure) and 3
(Validation rigor: risk limits, forward test, anti-overfitting statistics,
execution realism, position sizing) are complete. Next: M4 — Market State
Intelligence (anomaly detection, Market Regime Engine, scenario simulator).
