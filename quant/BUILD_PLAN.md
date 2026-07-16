# quantos — Build Plan (for Fable 5)

> **You are the builder.** Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) first — it
> defines the invariants (§0) and contracts you must honour. This file is your
> backlog: independently-shippable **work packages (WPs)**, dependency-ordered.
> Build one WP at a time, top to bottom, unless told otherwise.

## How to execute a work package

1. **Respect the invariants** (ARCHITECTURE §0). If a WP would break one, stop
   and flag it — do not "temporarily" disable a safety check.
2. **Build offline-first.** Every module needs a deterministic path that runs
   with no network and no API keys, plus a test proving it.
3. **Write the tests in the same WP.** Tests encode the acceptance criteria. The
   full suite must stay green and fast (`cd quant && python -m pytest`).
4. **Match the house style.** dataclasses for records, `Protocol` for ports,
   `as_dict()` for serialisation, docstrings at the density of existing modules,
   full type hints. Reuse existing types (`MarketSnapshot`, `Direction`,
   `AnalystOpinion`, `CommitteeDecision`) — never fork them.
5. **Commit per WP** with the WP id in the message, e.g. `WP-2.1: Store abstraction`.
6. **Update docs**: the module table in ARCHITECTURE §2.2 and the README when a
   WP lands.

Definition of done for every WP: *code + offline tests + docs updated +
invariants intact + suite green*.

---

# Milestone 2 — Data Lake  ⭐ build this next

Goal: turn the single `DataCollector` into a real, persisted, multi-channel Data
Lake that every downstream module can query — while staying fully offline-capable.

### WP-2.1 — Store abstraction (DuckDB/Parquet + Timescale)
- **Files:** `quantos/data/store.py`, `tests/test_store.py`.
- **Build:**
  - `class Store(Protocol)` per ARCHITECTURE §2.4 (`write`, `read`, `upsert`).
  - `DuckDBStore(path)` — default, offline. Backed by DuckDB over Parquet files;
    if `duckdb` is unavailable, fall back to a pure Parquet/pandas implementation
    so tests never require duckdb.
  - `TimescaleStore(dsn)` — optional (extra `[infra]`), lazy-imports psycopg;
    hypertable creation helper. Never imported unless explicitly constructed.
  - A `get_store(settings)` factory returning DuckDBStore by default.
- **Acceptance:** round-trip write→read of an OHLCV frame is loss-free; `upsert`
  on `(symbol, timestamp)` keys is idempotent (writing the same rows twice does
  not duplicate). Offline test uses DuckDBStore only.

### WP-2.2 — DataSource base + market source
- **Files:** `quantos/data/sources/base.py`, `quantos/data/sources/market.py`,
  `tests/test_sources_market.py`.
- **Build:**
  - `class DataSource(Protocol)` per §2.4 (`name`, `fetch`, `is_offline_capable`).
  - `MarketSource` wrapping the existing collector logic (ccxt + synthetic
    fallback) behind `fetch(symbol, start, end, timeframe)`.
- **Acceptance:** `MarketSource().fetch(...)` returns a normalised OHLCV frame
  offline; `is_offline_capable()` is `True`.

### WP-2.3 — Derivatives, on-chain, macro, sentiment, news sources
- **Files:** one module each under `quantos/data/sources/`
  (`derivatives.py`, `onchain.py`, `macro.py`, `sentiment.py`, `news.py`),
  plus `tests/test_sources_channels.py`.
- **Build:** each is a `DataSource` with a **synthetic offline generator** and an
  optional real backend (stub the real API behind a lazy import; do **not** hardcode
  any provider key). Output schemas:
  - derivatives: `funding_rate, open_interest, long_short_ratio, basis`
  - onchain: `net_exchange_flow, whale_accumulation, stablecoin_supply`
  - macro: `dxy, rates, cpi, event_flag` (event_flag names e.g. FOMC/NFP/CPI)
  - sentiment: `score` (-1..1) plus per-platform breakdown
  - news: rows of `{ts, source, headline, tag, sentiment}` (tagging can be a
    deterministic keyword stub now; real AI tagging is M6/optional)
- **Acceptance:** each source produces a deterministic frame offline with the
  documented columns; a test asserts columns + determinism per source.

### WP-2.4 — DataLake facade
- **Files:** `quantos/data/lake.py`, `tests/test_lake.py`.
- **Build:**
  - `class DataLake` composed of a `Store` + registered `DataSource`s.
  - `ingest(symbol, timeframe, start, end)` pulls each source and persists it.
  - `snapshot(symbol, timeframe, limit, channels=...) -> MarketSnapshot` reads
    from the store and assembles the **multi-channel** snapshot the committee
    already understands (populates `derivatives/onchain/macro/sentiment/events`).
- **Acceptance:** after `ingest`, `snapshot` returns a `MarketSnapshot` whose
  side-channels are populated so that **all 5 analysts participate (0 abstentions)**
  in `default_committee().deliberate(snapshot)`. Offline, deterministic.

### WP-2.5 — Wire CLI + docker-compose
- **Files:** extend `quantos/cli.py` (`ingest`, and `--from-lake` on `decide`),
  add `quant/docker-compose.yml` (timescaledb + redis + dashboard placeholder),
  `tests/test_cli_lake.py`.
- **Acceptance:** `quantos ingest --symbol BTC/USDT` runs offline against
  DuckDBStore; `quantos decide --from-lake` produces a 0-abstention decision.
  compose file lints (`docker compose config`) — no secrets committed.

---

# Milestone 3 — Risk Engine hardening + Forward test

### WP-3.1 — Risk limit library
- **Files:** `quantos/risk/limits.py`, `tests/test_risk_limits.py`.
- **Build:** composable rules (`VolatilitySpike`, `MacroEvent`, `DailyDrawdown`,
  `LowLiquidity`, `CorrelationBreak`, `MaxPositionSize`) each returning
  veto/warning; `RiskManager` refactored to run a configurable rule list while
  keeping its current constructor/behaviour (back-compatible).
- **Acceptance:** existing risk tests still pass; each rule has an isolated test;
  a single veto still blocks (I5).

### WP-3.2 — Forward test (out-of-sample simulation harness)
- **Files:** `quantos/backtest/forward.py`, `tests/test_forward.py`.
- **Build:** `forward_test(committee, ohlcv_stream, ...)` that steps a snapshot
  forward bar-by-bar feeding the paper engine, producing an equity curve — the
  bridge between walk-forward and paper trading in the funnel (I1 preserved).
- **Acceptance:** deterministic offline run; no look-ahead (I2); only paper.

---

# Milestone 4 — Anomaly detection + Scenario simulator

### WP-4.1 — Anomaly detector
- **Files:** `quantos/anomaly/base.py`, `quantos/anomaly/detectors.py`,
  `tests/test_anomaly.py`.
- **Build:** `AnomalyDetector` Protocol (§2.4). `IsolationForestDetector`
  (sklearn, extra `[ml]`) **and** a dependency-free `ZScoreDetector` baseline so
  tests run without sklearn. Detects volume spikes / volatility bursts / gaps.
- **Acceptance:** on a series with an injected spike, `flags()` marks the spike
  and not the calm region. Baseline test uses `ZScoreDetector` only.

### WP-4.2 — Anomaly context into the committee
- **Files:** small `AnomalyAnalyst` in `committee/analysts.py` (or an
  `events` enrichment), tests.
- **Acceptance:** an active anomaly surfaces in the decision (evidence or a risk
  warning/veto) and is visible in `explain_decision`.

### WP-4.3 — Scenario simulator
- **Files:** `quantos/scenarios/library.py`, `quantos/scenarios/simulator.py`,
  `tests/test_scenarios.py`.
- **Build:** named historical-style regimes (`COVID_CRASH`, `FTX`, `ETF_RALLY`,
  `BEAR_2022`, `BULL_2021`) as parameterised synthetic generators;
  `simulate(strategy_or_committee, scenario) -> BacktestResult`.
- **Acceptance:** each scenario yields a deterministic path with the expected
  qualitative shape (e.g. COVID_CRASH has a deep drawdown); simulate returns
  metrics without touching real capital.

---

# Milestone 5 — Strategy generator + Genetic evolution

### WP-5.1 — Strategy base + registry
- **Files:** `quantos/strategy/base.py`, `tests/test_strategy_base.py`.
- **Build:** `StrategySpec`, `Strategy` Protocol (§2.4), an
  `IndicatorStrategy` that turns a spec (indicators + params + rules) into a
  no-look-ahead target-position `signals(ohlcv)` series; a registry of building
  blocks (indicators + comparators).
- **Acceptance:** a spec round-trips to signals; signals never use future bars (I2).

### WP-5.2 — Strategy generator
- **Files:** `quantos/strategy/generator.py`, `tests/test_generator.py`.
- **Build:** `generate(n, seed, diversity)` producing N **distinct** specs
  (enforce indicator/param diversity; no duplicates). LLM-backed generation is an
  optional path behind `LLMClient`; the **default is deterministic** random-search
  over the building-block registry.
- **Acceptance:** `generate(100)` yields 100 unique specs offline; diversity
  metric above a threshold; each spec is a valid `Strategy`.

### WP-5.3 — Strategy lab (auto backtest + cull)
- **Files:** `quantos/strategy/lab.py`, `tests/test_lab.py`.
- **Build:** `StrategyLab.run(specs, ohlcv)` backtests each, ranks by a fitness
  (e.g. Sharpe with drawdown penalty), **culls** the weak, persists results to
  the `Store` and (optional) MLflow.
- **Acceptance:** ranking is deterministic offline; culling keeps the top-k;
  results are queryable from the store.

### WP-5.4 — Genetic evolution
- **Files:** `quantos/strategy/evolution.py`, `tests/test_evolution.py`.
- **Build:** `Genome` (encodes a spec's params), `Evolver` with selection /
  crossover / mutation over a fitness function. Dependency-free baseline GA;
  DEAP/Optuna optional accelerators behind `[research]`.
- **Acceptance:** on a fitness with a known optimum, mean population fitness
  **improves across generations** (deterministic with a fixed seed).

---

# Milestone 6 — LLM analysts + LangGraph debate  (optional infra)

### WP-6.1 — LLMClient port
- **Files:** `quantos/llm/client.py`, `tests/test_llm_client.py`.
- **Build:** `LLMClient` Protocol with a `complete(prompt, schema=None)` method;
  a `MockLLMClient` (deterministic, offline) as the test/default backend; adapters
  for Claude / OpenRouter / Ollama behind extra `[llm]` and lazy imports. No keys
  in code. Optional Langfuse tracing hook.
- **Acceptance:** committee runs with `MockLLMClient` offline; adapters import
  lazily and are never required for tests.

### WP-6.2 — LLM-backed analyst
- **Files:** `quantos/committee/llm.py`, `tests/test_llm_analyst.py`.
- **Build:** `LLMAnalyst(category, client)` that produces a valid
  `AnalystOpinion` **with evidence** from a structured LLM response; on any error
  or low-confidence parse it **abstains** (I3). Plugs into `InvestmentCommittee`
  with no committee changes (I7).
- **Acceptance:** with `MockLLMClient`, the analyst yields a valid opinion and
  the committee decision stays auditable (I4). Malformed response → abstain.

### WP-6.3 — LangGraph debate orchestrator (optional)
- **Files:** `quantos/committee/debate.py`, `tests/test_debate.py`.
- **Build:** an **alternative** orchestrator where analysts see a summary of peers
  and may revise once before the Chair decides. Must produce the same
  `CommitteeDecision` type. LangGraph optional; a plain-Python debate loop is the
  offline default.
- **Acceptance:** debate produces a valid auditable decision offline; risk veto
  still absolute (I5).

---

# Milestone 7 — Decision Archive + RAG memory + Continuous learning

### WP-7.1 — Decision Archive
- **Files:** `quantos/memory/archive.py`, `tests/test_archive.py`.
- **Build:** `DecisionArchive` persisting each `CommitteeDecision` (via `as_dict`)
  plus later outcome (`record_outcome(id, pnl, notes)`) to the `Store` — the
  per-trade "expediente" from vision item 10.
- **Acceptance:** decisions and outcomes round-trip; queryable by symbol/date.

### WP-7.2 — RAG memory
- **Files:** `quantos/memory/base.py`, `quantos/memory/rag.py`,
  `tests/test_rag.py`.
- **Build:** `MemoryStore` Protocol (§2.4). Offline default = a TF-IDF / keyword
  retriever over archived decisions (no external embedding service); pluggable
  embedding backend behind `[llm]`. Enables "6 months ago strategy 23 failed on
  CPI" recall as retrieved context for the committee.
- **Acceptance:** `query("CPI")` retrieves the CPI-tagged past decision offline.

### WP-7.3 — Continuous audit
- **Files:** `quantos/learning/audit.py`, `tests/test_audit.py`.
- **Build:** `audit(archive)` that mines closed trades for patterns (which analyst
  was most wrong, which regime hurt, indicator hit-rate) and emits a structured
  report + suggested weight adjustments for the `ConfidenceModel`.
- **Acceptance:** on a seeded archive with a known bad analyst, the audit
  identifies it and proposes lowering its weight.

---

# Milestone 8 — Dashboard + Observability

### WP-8.1 — Streamlit dashboard
- **Files:** `quantos/dashboard/app.py`, `quantos/dashboard/panels.py`,
  smoke test `tests/test_dashboard_import.py`.
- **Build:** panels for Equity curve, Drawdown, Sharpe/WinRate/ProfitFactor,
  open paper positions, latest committee decision ("AI thinking"), news/heatmaps.
  Reads the `Store` + `DecisionArchive`. Extra `[dashboard]`.
- **Acceptance:** app imports and builds its figures from a seeded store without a
  running server (import + figure-construction smoke test passes offline).
  Follow the `dataviz` skill for all charts.

### WP-8.2 — Observability
- **Files:** `quantos/obs/mlflow.py`, `quantos/obs/metrics.py`,
  compose additions, tests.
- **Build:** MLflow logging helper (local file backend offline) for backtests/GA;
  Prometheus metrics exporter for the paper engine + ingestors. All optional,
  lazy-imported.
- **Acceptance:** logging helper writes to a local MLflow dir in a test; metrics
  module exposes counters without requiring a running Prometheus.

---

## Global acceptance gate (every push)

- `cd quant && python -m pytest` is green and < ~5s.
- No network / no keys required for the suite.
- `grep -r "LiveExecutionDisabled" quantos/tests` still asserts I1 wherever
  execution is touched.
- ARCHITECTURE §2.2 module table and README reflect what shipped.

Build M2 first.
