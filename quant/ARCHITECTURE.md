# quantos — Architecture (master design)

> **Role split.** This document is written by the *architect* (Opus). It is the
> single source of truth for **what** the system is and **why**. The companion
> [`BUILD_PLAN.md`](./BUILD_PLAN.md) tells the *builder* (Fable 5) **how** to
> construct it, in independently-shippable work packages.

---

## 0. North star

`quantos` is an **AI quant research platform**, not a trading bot. It researches
markets, forms an evidence-based opinion through a multi-agent **Investment
Committee**, validates every idea through a rigorous backtest → walk-forward →
Monte Carlo → paper-trading funnel, and **only paper-trades**. Real order routing
is designed for but hard-disabled.

The value compounds in two assets that are hard to replicate: (1) the **Data
Lake** (months of tagged market/derivatives/on-chain/macro/sentiment/news data)
and (2) the **decision archive** (every committee decision and its outcome, fully
explainable and auditable).

### Non-negotiable invariants

These hold in **every** milestone. A change that violates any of them is wrong by
definition.

| # | Invariant | Enforced by |
| - | --------- | ----------- |
| I1 | **No real capital.** No code path places a live order. | `execution.build_execution_engine` raises `LiveExecutionDisabled`; only `is_paper` brokers accept orders. |
| I2 | **No look-ahead.** A value at bar *t* uses only data ≤ *t*; positions are lagged before P&L. | `backtest.engine`, indicator functions. |
| I3 | **Honest abstention.** An analyst with no data abstains; it never fabricates conviction. | `Analyst._abstain`, `abstained` flag excluded from aggregation. |
| I4 | **Auditability.** Every decision serialises to a complete record (analysts, evidence, confidence, risk). | `CommitteeDecision.as_dict()`. |
| I5 | **Risk veto is absolute.** One veto blocks the trade regardless of confidence. | `Chair.decide`. |
| I6 | **Runs offline, no secrets.** Every module has a deterministic offline path; keys are never required for research. | synthetic fallbacks, `.env.example`. |
| I7 | **Interfaces before implementations.** New capabilities plug into existing Protocols without refactoring the committee. | `Analyst`, `Broker`, `RiskGate`, `ExecutionEngine`, `DataSource`. |

---

## 1. Current state (Milestone 1 — DONE)

Already built and tested (`quant/quantos`, 34 passing tests):

```
data/        DataCollector (ccxt read-only + synthetic fallback), MarketSnapshot
features/    vectorised indicators (ema, rsi, atr, macd, bollinger, zscore, ...)
committee/   Analyst base + 5 analysts, ConfidenceModel, RiskManager (veto),
             Chair, InvestmentCommittee, CommitteeDecision
explain/     Bloomberg-style narrative + JSON decision report
backtest/    vectorised backtest (no look-ahead), walk-forward, Monte Carlo, metrics
paper/       PaperBroker with per-trade dossier (TradeRecord)
execution/   Broker / RiskGate / ExecutionEngine Protocols — DISABLED
cli.py       decide | backtest | walkforward | montecarlo | paper
```

The remaining milestones extend this spine. **They do not rewrite it.**

---

## 2. Target architecture

### 2.1 Layered view

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION      Dashboard (Streamlit)  ·  CLI  ·  REST API (opt)    │
├──────────────────────────────────────────────────────────────────────┤
│  ORCHESTRATION     InvestmentCommittee  ·  StrategyLab  ·  Scheduler   │
│                    (LangGraph optional for agent debate)              │
├──────────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE      Analysts (rule + LLM)  ·  Confidence  ·  Risk       │
│                    Anomaly detector  ·  Strategy generator + GA        │
│                    Memory (RAG)  ·  Scenario simulator                 │
├──────────────────────────────────────────────────────────────────────┤
│  RESEARCH          Backtest · Walk-forward · Monte Carlo · Paper       │
├──────────────────────────────────────────────────────────────────────┤
│  DATA LAKE         Ingestors → TimescaleDB (hot) + DuckDB/Parquet      │
│                    market · derivatives · on-chain · macro · sentiment │
│                    · news (AI-tagged)          Redis (cache/bus)       │
├──────────────────────────────────────────────────────────────────────┤
│  EXECUTION         Broker / RiskGate / ExecutionEngine  (PAPER ONLY)   │
├──────────────────────────────────────────────────────────────────────┤
│  OBSERVABILITY     MLflow (experiments) · Langfuse (LLM) · Prometheus  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 The 13 modules → concrete packages

| Vision module | Package(s) | Milestone | Key contract |
| ------------- | ---------- | --------- | ------------ |
| 1. Data Lake | `data.schema`✅, `data.store`✅, `data.connectors`✅ (foundation), `data.lake`, `data.ingest` | M2 🚧 (WP-2.1–2.4 done) | `Connector`, `Store`, `Schema` |
| 2. Multi-agent engine | `committee/*` (extend), `committee.llm` | M1✅ / M6 | `Analyst` |
| 3. Confidence system | `committee.confidence` | M1✅ | — |
| 4. Anomaly detector | `anomaly` | M4 | `AnomalyDetector` |
| 5. Strategy generator | `strategy.generator`, `strategy.lab` | M5 | `Strategy`, `StrategySpec` |
| 6. Genetic evolution | `strategy.evolution` | M5 | `Genome`, `Evolver` |
| 7. Pro backtesting | `backtest/*` (extend to forward test) | M1✅ / M3 | `BacktestResult` |
| 8. Risk engine | `committee.risk_manager` (extend), `risk.limits` | M1✅ / M3 | `RiskManager` |
| 9. Explainable AI | `explain/*` | M1✅ | — |
| 10. Continuous learning | `memory.archive`, `learning.audit` | M7 | `DecisionArchive` |
| 11. Dashboard | `dashboard/` (Streamlit) | M8 | reads Store + Archive |
| 12. Memory (RAG) | `memory.rag` | M7 | `MemoryStore` |
| 13. Scenario simulator | `scenarios` | M4 | `Scenario` |

### 2.3 Core data contracts (already established — reuse, don't reinvent)

```python
# data/models.py
MarketSnapshot(symbol, timeframe, ohlcv, derivatives, onchain, macro,
               sentiment, events, news)   # analysts read whatever is present

# committee/base.py
Direction(LONG|FLAT|SHORT)
Evidence(name, detail, impact:[-1,1], value)     # signed, auditable
AnalystOpinion(analyst, category, direction, confidence:[0,1], evidence, abstained)
class Analyst(ABC): def analyze(snapshot, context) -> AnalystOpinion

# committee/decision.py
CommitteeDecision(symbol, timeframe, price, direction, approved, confidence,
                  blocked_by_risk, reasons, opinions, confidence_report, risk)

# execution/interfaces.py  (Protocols — new engines must satisfy these)
Broker(is_paper, submit, equity)
RiskGate(allow(decision) -> bool)
ExecutionEngine(execute(decision, price))
```

### 2.4 New contracts to introduce (specified for the builder)

```python
# data/sources/base.py  — every ingestor implements this
class DataSource(Protocol):
    name: str
    def fetch(self, symbol: str, start, end, **kw) -> pandas.DataFrame: ...
    def is_offline_capable(self) -> bool: ...   # must have a synthetic/offline mode

# data/store.py — persistence abstraction (Timescale in prod, DuckDB/Parquet offline)
class Store(Protocol):
    def write(self, table: str, df) -> int: ...
    def read(self, table: str, symbol=None, start=None, end=None) -> "DataFrame": ...
    def upsert(self, table: str, df, keys: list[str]) -> int: ...

# anomaly/base.py
class AnomalyDetector(Protocol):
    def fit(self, df) -> "AnomalyDetector": ...
    def score(self, df) -> "Series": ...        # higher = more anomalous
    def flags(self, df) -> "Series[bool]": ...

# strategy/base.py
@dataclass
class StrategySpec: name; params: dict; indicators: list[str]; rationale: str
class Strategy(Protocol):
    spec: StrategySpec
    def signals(self, ohlcv) -> "Series[float]"   # target position -1..1, no look-ahead

# memory/base.py
class MemoryStore(Protocol):
    def add(self, doc: dict) -> str: ...
    def query(self, text: str, k: int = 5, filters: dict | None = None) -> list[dict]: ...
```

Everything above is designed so an **LLM-backed analyst**, a **live broker**, a
**new data source**, or a **generated strategy** slots in without touching the
committee.

---

## 3. Tech stack (decisions + rationale)

| Concern | Choice | Rationale / offline fallback |
| ------- | ------ | ---------------------------- |
| Language | Python ≥3.10 | matches vision + ecosystem |
| Core deps | numpy, pandas | already in use; keep the core dependency-light |
| Time-series store | **TimescaleDB** (hot) | SQL + hypertables for tick/OHLCV; offline fallback **DuckDB + Parquet** |
| Cache / bus | **Redis** | quotes cache, pub/sub; offline fallback = in-process dict/queue |
| Market/derivs data | **ccxt** (read-only) | already wired; synthetic generator when absent |
| On-chain / macro / sentiment | pluggable `DataSource`s | each ships a synthetic offline mode (I6) |
| Backtesting | in-house vectorised (done) + **vectorbt** (optional, heavy scans) | in-house always available |
| Perf reporting | **QuantStats** (optional) | our `metrics.py` is the always-on baseline |
| ML / anomaly | scikit-learn, **PyOD**, **Prophet** | Isolation Forest baseline is sklearn-only |
| Optimisation / GA | **Optuna**, **DEAP**, Nevergrad | GA baseline implemented without heavy deps first |
| Agent orchestration | **LangGraph** (optional) for debate | committee works without it; LangGraph is an alt orchestrator |
| LLM access | **Claude** (primary), OpenRouter/Ollama pluggable | via a thin `LLMClient` port; rule-based analysts remain the offline default |
| Dashboard | **Streamlit** (primary), Grafana for infra metrics | reads Store + DecisionArchive |
| Experiment tracking | **MLflow** | logs backtests/GA runs; local file backend offline |
| LLM observability | **Langfuse** (optional) | traces analyst/LLM calls |
| Infra metrics | Prometheus + Grafana | scrape ingestors + paper engine |
| Packaging | Docker + docker-compose | one command spins Timescale+Redis+dashboard |
| CI | GitHub Actions | run `pytest` offline on every push |

> **Dependency policy.** The **core** (`data`, `committee`, `backtest`, `paper`,
> `explain`, `execution`) stays importable with only numpy+pandas. Everything
> heavier lives behind optional extras (`[data]`, `[research]`, `[ml]`, `[llm]`,
> `[dashboard]`) and lazy imports. This preserves I6.

---

## 4. Repository evolution

```
quant/
├── pyproject.toml            # add extras: ml, llm, dashboard, infra
├── docker-compose.yml        # NEW (M2): timescaledb + redis + dashboard
├── ARCHITECTURE.md           # this file
├── BUILD_PLAN.md             # work packages for Fable 5
├── quantos/
│   ├── data/
│   │   ├── collector.py            # exists
│   │   ├── models.py               # exists
│   │   ├── store.py                # NEW  Store + DuckDBStore + TimescaleStore
│   │   ├── lake.py                 # NEW  DataLake facade (orchestrates sources→store)
│   │   └── sources/                # NEW  one module per feed, all DataSource
│   │       ├── base.py  market.py  derivatives.py  onchain.py
│   │       ├── macro.py  sentiment.py  news.py
│   ├── features/                   # exists (extend with derivative features)
│   ├── committee/                  # exists (add committee/llm.py in M6)
│   ├── anomaly/                    # NEW (M4)
│   ├── strategy/                   # NEW (M5)  base, generator, lab, evolution
│   ├── memory/                     # NEW (M7)  archive, rag, base
│   ├── learning/                   # NEW (M7)  audit
│   ├── scenarios/                  # NEW (M4)  library + simulator
│   ├── explain/  backtest/  paper/  execution/   # exist
│   └── dashboard/                  # NEW (M8)  Streamlit app
└── tests/                          # mirror every new package, offline & deterministic
```

---

## 5. Milestone roadmap (dependency-ordered)

```
M1 ✅ Investment Committee vertical slice            [DONE]
M2    Data Infrastructure (professional)             → unlocks real data for all
      └─ detailed design: docs/DATA_INFRASTRUCTURE.md (connector framework,
         schema versioning, validation, resilient 24/7 ingestion, feature store)
M3    Risk Engine hardening + Forward test           → completes the validation funnel
M4    Anomaly detection + Scenario simulator          (depend on M2)
M5    Strategy generator + Genetic evolution + Lab    (depend on M2, M3)
M6    LLM-backed analysts + LangGraph debate          (depend on M1; optional infra)
M7    Decision Archive + RAG memory + Continuous audit(depend on M2, M5)
M8    Dashboard + Observability (MLflow/Prometheus)   (depend on M2, M3, M7)
```

Each milestone is a set of **work packages** (WPs) in `BUILD_PLAN.md`. A WP is
sized to be built and tested in one focused pass, ships with tests, and preserves
every invariant in §0.

---

## 6. Cross-cutting conventions (bind on the builder)

1. **Match the existing code.** Same docstring density, dataclasses for records,
   Protocols for ports, `as_dict()` for serialisation, type hints throughout.
2. **Offline-first.** Every new `DataSource`/module ships a deterministic
   synthetic path and a test that runs with no network and no keys.
3. **Tests are part of the WP.** No WP is "done" without deterministic tests that
   assert its acceptance criteria. Target: the suite stays green and fast (<5s).
4. **No secrets in code or git.** New config via `Settings` + `.env.example`.
5. **Preserve safety.** If a WP touches execution, it must keep I1 provably true
   (add/extend a test that asserts `LiveExecutionDisabled`).
6. **Small, reviewable commits** per WP with the WP id in the message.
7. **Docs.** Update the module table here and the README when a WP lands.

---

## 7. How a decision flows end-to-end (target state)

```
DataLake.snapshot(symbol, tf)                    # M2: real multi-channel snapshot
   └─ AnomalyDetector flags regime               # M4: attach anomaly context
        └─ InvestmentCommittee.deliberate()      # M1: analysts → confidence → risk
             ├─ (M6) LLM analysts join the panel
             └─ Chair.decide()  ── RiskManager veto ─▶ blocked?
                  └─ CommitteeDecision (auditable)
                       ├─ explain_decision()      # M1: narrative
                       ├─ DecisionArchive.record() # M7: dossier + outcome later
                       └─ PaperExecutionEngine.execute()  # paper only (I1)
StrategyLab (M5) continuously invents/backtests/evolves strategies whose signals
can feed the StatisticalAnalyst or spawn new analysts.
Dashboard (M8) renders equity, drawdown, Sharpe, open positions, "AI thinking".
```

This is the architecture. Build it in the order and shape defined by
`BUILD_PLAN.md`.
