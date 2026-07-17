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
python -m quantos.cli backtest   --symbol BTC/USDT --bars 400   # committee backtest + baselines
python -m quantos.cli walkforward --symbol BTC/USDT --bars 600  # out-of-sample folds
python -m quantos.cli montecarlo --symbol BTC/USDT --bars 400   # resampled risk profile
python -m quantos.cli paper      --symbol BTC/USDT --bars 400   # decide + paper execution
```

Every command runs offline and is reproducible for a fixed `--seed`.

## Layout (Milestone 1 — shipped)

```
quantos/
├── config.py                Settings (env-driven, offline defaults)
├── data/                    MarketSnapshot + read-only collector (synthetic fallback)
├── features/                causal technical indicators (no look-ahead)
├── committee/               analysts, confidence model, risk veto, chair, decision
├── explain/                 explain_decision / decision_report
├── backtest/                engine (lagged positions), walk-forward, Monte Carlo,
│                            metrics, buy-and-hold + random baselines
├── paper/                   PaperBroker + per-trade dossier (TradeRecord)
├── execution/               Broker/RiskGate/ExecutionEngine ports; live HARD-DISABLED
└── cli.py                   decide | backtest | walkforward | montecarlo | paper
```

## Tests

```bash
cd quant && python -m pytest        # offline, deterministic, fast
```

## Status

Milestone 1 (Investment Committee) is complete. Next: M2 — Data Infrastructure
(connectors, schema registry, tiered store, feature store, DataLake facade).
