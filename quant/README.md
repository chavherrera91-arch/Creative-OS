# quantos — AI Quant Research Platform

> **Research-first. No real capital.** Live order routing is hard-disabled in
> code. This platform researches markets, forms an evidence-based opinion through
> a multi-agent **Investment Committee**, and only ever paper-trades.

`quantos` is the first milestone of a larger quantitative research platform. It
implements the differentiating feature end-to-end — a committee of specialist
analysts whose evidence is aggregated into a confidence score, gated by a Risk
Manager that can **veto** any trade — plus the research tooling to validate what
the committee decides (backtest → walk-forward → Monte Carlo → paper trading).

## Why a committee?

Instead of one opaque model shouting "buy BTC", each analyst presents its
evidence. A confidence model combines them; the Chair decides; the Risk Manager
can overrule everyone. When a trade goes wrong you can see **exactly which
analyst contributed which evidence** and fix that component in isolation.

```
Technical ─┐
Statistical┤
Macro      ├─► Confidence Model ─► Chair ─► Decision
Sentiment  ┤          ▲
On-chain  ─┘          │
                 Risk Manager  ── can VETO ──► trade blocked
```

## What's implemented (this milestone)

| Module | Status | Location |
| --- | --- | --- |
| Data Collector (read-only, ccxt + synthetic fallback) | ✅ | `quantos/data/` |
| Technical indicators | ✅ | `quantos/features/` |
| Investment Committee (analysts, confidence, Chair) | ✅ | `quantos/committee/` |
| Risk Manager (veto engine) | ✅ | `quantos/committee/risk_manager.py` |
| Explainability engine | ✅ | `quantos/explain/` |
| Backtesting (vectorised, no look-ahead) | ✅ | `quantos/backtest/engine.py` |
| Walk-forward analysis | ✅ | `quantos/backtest/walk_forward.py` |
| Monte Carlo robustness | ✅ | `quantos/backtest/monte_carlo.py` |
| Paper trading (with per-trade dossier) | ✅ | `quantos/paper/` |
| Broker / RiskGate / ExecutionEngine interfaces | 🔒 decoupled & **disabled** | `quantos/execution/` |

Deliberately **not** wired to real money: any attempt to build a live execution
engine raises `LiveExecutionDisabled`. The paper broker is the only execution
path. Macro / sentiment / on-chain analysts **abstain honestly** when their data
channel is absent rather than fabricating conviction.

## Install

```bash
cd quant
python -m pip install -e ".[dev]"        # core + pytest
# optional extras:
#   pip install -e ".[data]"      # ccxt for real read-only market data
#   pip install -e ".[research]"  # vectorbt, quantstats, sklearn, optuna
```

No exchange keys are required. Without `ccxt`, a deterministic synthetic data
generator is used so everything runs offline.

## Use it

```bash
# One committee decision, fully explained
quantos decide --symbol BTC/USDT --timeframe 1h --bars 400

# Committee-driven backtest
quantos backtest --symbol BTC/USDT --bars 1500 --step 8

# Out-of-sample walk-forward
quantos walkforward --symbol BTC/USDT --bars 2000 --folds 5

# Monte Carlo robustness of the backtest
quantos montecarlo --symbol BTC/USDT --bars 1500 --sims 2000

# Paper trade the committee (no real money)
quantos paper --symbol BTC/USDT --bars 1500 --step 8
```

Programmatic:

```python
from quantos.data.collector import DataCollector
from quantos.committee.committee import default_committee
from quantos.explain.explainer import explain_decision

snapshot = DataCollector().snapshot("BTC/USDT", "1h", 400, context={
    "macro": {"dxy_trend": -0.4, "rate_bias": -0.3, "risk_on": 0.6},
    "sentiment": {"score": 0.5},
    "onchain": {"net_exchange_flow": -0.6, "whale_accumulation": 0.7},
    "events": {"FOMC": False},
})
decision = default_committee().deliberate(snapshot)
print(explain_decision(decision))
```

## Design principles

- **Research-first & safe by default** — no real capital, live execution gated
  behind an explicit choke point that currently always refuses.
- **Auditable** — every decision carries the analysts, their evidence, the
  confidence breakdown and the risk assessment (`decision.as_dict()`).
- **Modular & production-ready** — analysts, confidence model, risk manager and
  execution all sit behind clean interfaces, so an LLM-backed analyst or a live
  broker can be added later **without refactoring** the committee.
- **No look-ahead** — indicators and the backtester only use information
  available up to each bar; positions are lagged before being applied.

## Tests

```bash
cd quant && python -m pytest      # 34 offline, deterministic tests
```

## Roadmap (next milestones)

Data Lake (TimescaleDB/DuckDB) · derivatives & on-chain feeds · anomaly detection
(Isolation Forest / PyOD) · automatic strategy generation & genetic evolution
(DEAP / Optuna) · RAG memory of past regimes · scenario simulator (COVID / FTX /
ETF) · Streamlit/Grafana dashboard · MLflow / Langfuse observability. Execution
stays disabled until deliberately enabled.
