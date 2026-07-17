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

# Milestone 1 — Investment Committee  ⭐ build this first

Goal: the platform's differentiator, end-to-end and offline — specialist analysts
whose evidence is aggregated into a confidence score, a Risk Manager that can
**veto**, a Chair that renders an auditable decision, the explainability report,
and the backtest→walk-forward→Monte Carlo→paper funnel to validate what the
committee decides. No real capital (I1). This milestone also creates the core
types (`MarketSnapshot`, `Direction`, `Evidence`, `AnalystOpinion`,
`CommitteeDecision`) every later milestone reuses.

Dependency order within M1: 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8.

### WP-1.1 — Package skeleton + config + core data model
- **Files:** `quant/pyproject.toml`, `quant/.env.example`, `quant/.gitignore`,
  `quant/README.md`, `quantos/__init__.py`, `quantos/config.py`,
  `quantos/data/models.py` (`MarketSnapshot`), `quantos/data/collector.py`
  (read-only ccxt + deterministic synthetic fallback), `tests/test_data.py`,
  `tests/conftest.py`.
- **Build:** offline-first packaging (extras: `data`, `research`, `dev`);
  `Settings` from env with defaults; `MarketSnapshot` carrying OHLCV + optional
  derivatives/onchain/macro/sentiment/events/news channels; a `DataCollector`
  that never places orders and falls back to a seeded synthetic generator.
- **Acceptance:** synthetic data is deterministic; `MarketSnapshot` validates its
  OHLCV columns; everything imports and tests run with only numpy+pandas (I6).

### WP-1.2 — Technical indicators
- **Files:** `quantos/features/indicators.py`, `tests/test_indicators.py`.
- **Build:** vectorised, no-look-ahead `ema/sma/rsi/atr/macd/bollinger/zscore/
  returns/rolling_volatility`.
- **Acceptance:** each indicator matches a hand-checked value on a fixture; no
  value at bar *t* uses data > *t* (I2).

### WP-1.3 — Analyst base + specialist analysts
- **Files:** `quantos/committee/base.py` (`Direction`, `Evidence`,
  `AnalystOpinion`, `Analyst` ABC with `_abstain`), `committee/analysts.py`
  (Technical, Statistical, Macro, Sentiment, On-chain), `tests/test_analysts.py`.
- **Build:** each analyst emits an `AnalystOpinion` with signed `Evidence`;
  data-hungry analysts **abstain** when their channel is absent (I3).
- **Acceptance:** technical analyst is bullish on an uptrend fixture; a data-less
  macro/sentiment/onchain analyst abstains; every opinion carries evidence.

### WP-1.4 — Confidence model
- **Files:** `quantos/committee/confidence.py`, `tests/test_confidence.py`.
- **Build:** weighted aggregation over categories → `ConfidenceReport`
  (composite direction, confidence, agreement, per-category, abstentions,
  `meets_threshold`). Abstentions excluded from the denominator (I3).
- **Acceptance:** agreement + threshold logic verified; all-abstain → FLAT.

### WP-1.5 — Risk Manager (veto) + Chair + decision
- **Files:** `quantos/committee/risk_manager.py` (`RiskAssessment`),
  `committee/chair.py`, `committee/decision.py` (`CommitteeDecision` with
  `regime`/`strategies_considered`/`run_manifest` fields, defaulting empty in
  M1), `committee/committee.py` (`InvestmentCommittee`, `default_committee`),
  `tests/test_risk_and_chair.py`.
- **Build:** Risk rules (volatility spike, macro event, daily drawdown, low
  liquidity) returning veto/warning; Chair decision hierarchy (regime gate ▶ risk
  veto ▶ threshold). A veto forces FLAT regardless of confidence (I5).
- **Acceptance:** a unanimous LONG is blocked by a single veto; below-threshold
  stands down; decision serialises fully via `as_dict()` (I4).

### WP-1.6 — Explainability engine
- **Files:** `quantos/explain/explainer.py`, `tests/test_explain.py`.
- **Build:** `explain_decision(decision) -> str` (Decision / Confidence /
  Reasons-for / Reasons-against / Risks / Analyst panel / Chair) and
  `decision_report(decision) -> dict` (JSON-serialisable).
- **Acceptance:** report shows a surfaced veto; JSON report is serialisable (I4).

### WP-1.7 — Backtest funnel (backtest / walk-forward / Monte Carlo)
- **Files:** `quantos/backtest/metrics.py`, `backtest/engine.py`
  (`backtest`, `committee_signals`), `backtest/walk_forward.py`,
  `backtest/monte_carlo.py`, `tests/test_backtest.py`.
- **Build:** vectorised backtest with costs and **lagged positions** (I2);
  committee-driven signal generation; walk-forward OOS folds; Monte Carlo
  resampling with percentiles + prob-of-loss.
- **Acceptance:** flat positions → ~0 return; a late-only position cannot affect
  prior bars (no look-ahead); metrics finite; MC percentiles ordered.

### WP-1.8 — Paper trading + disabled execution interfaces + CLI
- **Files:** `quantos/paper/broker.py` (`PaperBroker`, `TradeRecord` dossier),
  `quantos/execution/interfaces.py` (`Broker`/`RiskGate`/`ExecutionEngine`
  Protocols, `PaperExecutionEngine`, `build_execution_engine` raising
  `LiveExecutionDisabled`), `quantos/cli.py` (`decide|backtest|walkforward|
  montecarlo|paper`), `tests/test_paper_and_execution.py`.
- **Build:** paper broker with fees/slippage and a per-trade dossier; execution
  layer that **refuses** any live/non-paper engine (I1).
- **Acceptance:** `build_execution_engine(live=True)` raises; a non-paper broker
  is rejected; `quantos decide` prints a full explainable decision offline.

### M1 milestone gate
Committee runs offline end-to-end; a veto is absolute; the backtest funnel has no
look-ahead; live execution is provably disabled; suite green/offline/fast.

---

# Milestone 2 — Data Infrastructure (professional)

Goal: a **professional, modular, schema-versioned, validated, monitored** data
platform designed to run **24/7 for years**, where each source is an independent
plug-in connector added **without touching the core**. The Data Lake is the
platform's primary asset, optimised for research, backtesting, ML and real-time.

> **Read [`docs/DATA_INFRASTRUCTURE.md`](./docs/DATA_INFRASTRUCTURE.md) in full
> before building** — it holds the principles, the component map, and the exact
> contract signatures. The WPs below are the build order; the doc is the detail.

Dependency order within M2: 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7 → 2.8 → 2.9.

### WP-2.1 — Schema system (versioned)
- **Files:** `quantos/data/schema/base.py`, `schema/registry.py`,
  `schema/validation.py`, `tests/test_schema.py`.
- **Build:** `FieldSpec`, `Schema`, `SchemaRegistry` (register/latest/get),
  `Migration` + `migrate()`, `DataValidator` → `ValidationReport` (required cols,
  dtype coercion, non-null, PK uniqueness, monotonic `event_time`, min/max range).
- **Acceptance:** two schema versions + a migration transform a v1 frame to v2;
  validator rejects a frame missing a required column / with duplicate PKs /
  with a non-monotonic time column; returns a cleaned frame + accurate report.

### WP-2.2 — Store (tiered: raw / curated / features)
- **Files:** `quantos/data/store/base.py`, `store/duckdb_store.py`,
  `store/timescale_store.py`, `tests/test_store.py`.
- **Build:** `Store` Protocol with tiers (`raw|curated|features`) and
  `write/upsert/read/tables`. `DuckDBStore` default (DuckDB over Parquet; pure
  pandas/Parquet fallback if `duckdb` absent so tests never require it).
  `TimescaleStore` optional (`[infra]`, lazy psycopg, hypertable helper).
- **Acceptance:** loss-free round-trip per tier; `upsert` on PK is idempotent
  (writing identical rows twice does not grow the table). Offline test uses
  DuckDBStore only.

### WP-2.3 — Connector framework + registry (self-registration)
- **Files:** `quantos/data/connectors/base.py`, `connectors/registry.py`,
  `tests/test_connectors_registry.py`.
- **Build:** `ConnectorMetadata`, `FetchRequest`, `FetchResult`, `HealthStatus`,
  `Connector` ABC (`fetch`, `synthetic`, `healthcheck`); module-level
  `registry` + `@register` class decorator. Discovery is registry-based; **no core
  file references a specific connector**.
- **Acceptance:** a dummy `@register`ed connector appears in `registry.all()` and
  `by_category()`; registering requires **zero edits** to base/registry/lake.

### WP-2.4 — Market connector
- **Files:** `quantos/data/connectors/market.py`, `tests/test_connector_market.py`.
- **Build:** OHLCV connector reusing the existing ccxt+synthetic logic behind the
  `Connector` interface, emitting rows with `symbol, event_time, ingested_at,
  open, high, low, close, volume` against a registered `market` schema.
- **Acceptance:** `synthetic` mode is deterministic and schema-valid; `fetch` in
  `auto` mode works offline (falls back to synthetic).

### WP-2.5 — Derivatives / on-chain / macro / sentiment / news connectors
- **Files:** `connectors/{derivatives,onchain,macro,sentiment,news}.py`,
  `tests/test_connectors_channels.py`.
- **Build:** one `@register`ed `Connector` each, all with deterministic
  `synthetic` modes and lazy-imported optional real backends (no hardcoded keys).
  Schemas per `docs/DATA_INFRASTRUCTURE.md` §2. News tagging is a deterministic
  keyword stub now (AI tagging is M6).
- **Acceptance:** each connector produces a schema-valid deterministic frame
  offline; a test asserts schema conformance + determinism per connector.

### WP-2.6 — Resilient ingestion runner
- **Files:** `quantos/data/ingest/retry.py`, `ingest/watermark.py`,
  `ingest/runner.py`, `tests/test_ingest_runner.py`.
- **Build:** `RetryPolicy` (exponential backoff + jitter), `CircuitBreaker`,
  `Watermark` store (per connector+symbol, persisted via `Store`),
  `IngestionRunner.run` = circuit gate → fetch-with-retries → validate → write raw
  + upsert curated → advance watermark → record health. Fully idempotent.
- **Acceptance:** a connector that raises K times is retried per policy then
  succeeds; after `failure_threshold` failures the breaker opens; a second `run`
  over the same window does not duplicate curated rows (watermark + upsert).

### WP-2.7 — Gaps, scheduler, health monitor (24/7)
- **Files:** `quantos/data/ingest/gaps.py`, `ingest/scheduler.py`,
  `quantos/data/quality/monitor.py`, `tests/test_ops.py`.
- **Build:** gap detection vs cadence + backfill; `Scheduler` with
  `(connector, symbol, cadence)` jobs and an offline-testable `run_due(now)`;
  `HealthMonitor` (freshness/lag, success rate, rows/interval, last error).
- **Acceptance:** an injected missing timestamp is detected and repaired;
  `run_due` dispatches only due jobs; `HealthMonitor` flags a stale connector.

### WP-2.8 — Catalog, FeatureStore (point-in-time), DataLake facade
- **Files:** `quantos/data/catalog.py`, `quantos/data/featurestore.py`,
  `quantos/data/lake.py`, `tests/test_featurestore.py`, `tests/test_lake.py`.
- **Build:** `DataCatalog` (datasets, schema+version, freshness, lineage);
  `FeatureStore.as_of(symbol, at, features)` via backward as-of join (**never
  returns event_time > at**, I2); `DataLake` facade (`ingest`, `repair_gaps`,
  `snapshot(..., at=None)`, `catalog`, `health`).
- **Acceptance:** explicit no-look-ahead test on `as_of`; after `ingest`,
  `DataLake.snapshot(...)` yields a `MarketSnapshot` where
  `default_committee().deliberate(snapshot)` has **0 abstentions**;
  `health()` reports per-connector freshness.

### WP-2.9 — CLI + compose wiring
- **Files:** extend `quantos/cli.py` (`ingest`, `catalog`, `health`, and
  `--from-lake` on `decide`), `quant/docker-compose.yml`
  (timescaledb + redis + dashboard placeholder), `tests/test_cli_lake.py`.
- **Acceptance:** `quantos ingest --symbol BTC/USDT` runs offline against
  DuckDBStore; `quantos decide --from-lake` gives a 0-abstention decision;
  `docker compose config` lints; **no secrets committed**.

### M2 milestone gate (professional bar)
All eight acceptance points in `docs/DATA_INFRASTRUCTURE.md` §7 pass, the suite
is green/offline/fast, and adding a source provably needs **zero core edits**.

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

# Milestone 4 — Market State Intelligence (anomaly + regime + scenarios)

Goal: teach the platform to read the *state* of the market. This milestone
delivers the **Market Regime Engine** (module 14) whose classification, together
with the Meta-Learner (M7), drives "select only strategies validated for this
regime." All classifications are explainable (evidence) and reproducible (I8).

### WP-4.1 — Anomaly detector
- **Files:** `quantos/anomaly/base.py`, `quantos/anomaly/detectors.py`,
  `tests/test_anomaly.py`.
- **Build:** `AnomalyDetector` Protocol (ARCHITECTURE §2.4).
  `IsolationForestDetector` (sklearn, extra `[ml]`) **and** a dependency-free
  `ZScoreDetector` baseline so tests run without sklearn. Detects volume spikes /
  volatility bursts / gaps / suspected wash-trading & fake liquidity patterns.
- **Acceptance:** on a series with an injected spike, `flags()` marks the spike
  and not the calm region. Baseline test uses `ZScoreDetector` only.

### WP-4.2 — Regime feature set
- **Files:** `quantos/features/regime_features.py`, `tests/test_regime_features.py`.
- **Build:** no-look-ahead features that characterise state: trend strength (ADX /
  EMA slope), realised & ATR volatility, range vs trend (e.g. Hurst / efficiency
  ratio), volume regime, and macro-event proximity (from the `events` channel).
- **Acceptance:** each feature is deterministic and uses only data ≤ *t* (I2);
  trend fixture scores high trend-strength, choppy fixture scores low.

### WP-4.3 — Market Regime Engine  (module 14)
- **Files:** `quantos/regime/base.py` (`RegimeState`, `RegimeClassifier`
  Protocol), `quantos/regime/classifier.py` (`RuleRegimeClassifier` baseline; an
  optional `HmmRegimeClassifier`/`GmmRegimeClassifier` behind `[ml]`),
  `tests/test_regime.py`.
- **Build:** `classify(snapshot) -> RegimeState` returning a label
  (`TREND_UP|TREND_DOWN|RANGE|HIGH_VOL|LOW_VOL|MACRO_EVENT|CRISIS`), class
  probabilities, the driving features, and **`Evidence`** explaining the call.
  The rule baseline needs no ML dependency. Classification is deterministic (I8).
- **Acceptance:** a strong-uptrend fixture classifies `TREND_UP` with supporting
  evidence; a high-ATR/spike fixture classifies `HIGH_VOL` or `CRISIS`; a macro
  `events` flag forces `MACRO_EVENT`. Same input → same output (reproducible).

### WP-4.4 — Regime into the committee context
- **Files:** an `AnomalyAnalyst` and regime enrichment in `committee/analysts.py`
  / the deliberation context; extend `CommitteeDecision.regime`; tests.
- **Build:** the committee receives `regime` + `anomalies` in its context; the
  Chair's **regime gate** (ARCHITECTURE §3) can stand down in an untradeable
  regime; the decision records the active regime (I4). No Meta-Learner yet (M7).
- **Acceptance:** an active anomaly surfaces in `explain_decision`; the decision
  carries the classified regime; an untradeable-regime fixture stands down.

### WP-4.5 — Scenario simulator
- **Files:** `quantos/scenarios/library.py`, `quantos/scenarios/simulator.py`,
  `tests/test_scenarios.py`.
- **Build:** named historical-style regimes (`COVID_CRASH`, `FTX`, `ETF_RALLY`,
  `BEAR_2022`, `BULL_2021`) as parameterised synthetic generators;
  `simulate(strategy_or_committee, scenario) -> BacktestResult`. Each scenario
  also labels its ground-truth regime so the Regime Engine can be scored against it.
- **Acceptance:** each scenario yields a deterministic path with the expected
  qualitative shape (COVID_CRASH → deep drawdown); the Regime Engine recovers the
  scenario's labelled regime on its core segment; no real capital touched.

---

# Milestone 5 — Strategy Lab: AI generator + Genetic evolution

Goal: the platform *invents* strategies rather than having them hand-coded, then
auto-validates and culls them. Each strategy declares the **regime(s) it targets**
so the Meta-Learner (M7) can map families → regimes.

### WP-5.1 — Strategy base + registry
- **Files:** `quantos/strategy/base.py`, `tests/test_strategy_base.py`.
- **Build:** `StrategySpec` (with `version`, `family`, and `target_regimes`),
  `Strategy` Protocol (ARCHITECTURE §2.4), an `IndicatorStrategy` that turns a
  spec (indicators + params + rules) into a no-look-ahead target-position
  `signals(ohlcv)` series; a registry of building blocks (indicators +
  comparators). Specs are hashable/versioned for reproducibility (I8).
- **Acceptance:** a spec round-trips to signals; signals never use future bars
  (I2); the same spec always yields the same signals.

### WP-5.2 — Strategy generator (AI-invented)
- **Files:** `quantos/strategy/generator.py`, `tests/test_generator.py`.
- **Build:** `generate(n, seed, diversity)` producing N **distinct** specs.
  Two backends behind one interface: (a) a **deterministic** random/grammar
  search over the building-block registry (default, offline) and (b) an optional
  **LLM backend** (`LLMClient`, M6) where Claude proposes original strategies with
  a stated `rationale` and `target_regimes`. Diversity is enforced (no duplicate
  indicator sets; a diversity metric gate). Generated specs are validated to be
  runnable `Strategy`s before they leave the generator.
- **Acceptance:** `generate(100)` yields 100 unique, valid specs offline and
  deterministically for a fixed seed; diversity metric above threshold; the LLM
  path is exercised with `MockLLMClient` and never required for tests.

### WP-5.3 — Strategy lab (auto backtest + cull)
- **Files:** `quantos/strategy/lab.py`, `tests/test_lab.py`.
- **Build:** `StrategyLab.run(specs, ohlcv)` backtests each (reusing the M1
  funnel), ranks by a fitness (e.g. Sharpe with drawdown penalty), **culls** the
  weak, and persists results + the per-strategy regime it was tested under to the
  `Store` (and optional MLflow) — the raw material the Meta-Learner consumes.
- **Acceptance:** ranking is deterministic offline; culling keeps the top-k;
  results (including tested regime) are queryable from the store.

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

# Milestone 7 — Memory & Learning (archive + RAG + audit + meta-learning)

Goal: close the loop. Persist every decision + outcome, recall past regimes,
audit what failed, and — the headline — **learn which strategy families work in
which regime** so the platform selects only regime-validated strategies before
each decision.

### WP-7.1 — Decision Archive
- **Files:** `quantos/memory/archive.py`, `tests/test_archive.py`.
- **Build:** `DecisionArchive` persisting each `CommitteeDecision` (via `as_dict`,
  including `regime`, `strategies_considered` and `run_manifest`) plus later
  outcome (`record_outcome(id, pnl, notes)`) to the `Store` — the per-trade
  "expediente" from vision item 10. Reproducible via the stored manifest (I8).
- **Acceptance:** decisions and outcomes round-trip; queryable by symbol / date /
  regime; the stored manifest is sufficient to replay the decision.

### WP-7.2 — RAG memory
- **Files:** `quantos/memory/base.py`, `quantos/memory/rag.py`,
  `tests/test_rag.py`.
- **Build:** `MemoryStore` Protocol (ARCHITECTURE §2.4). Offline default = a
  TF-IDF / keyword retriever over archived decisions (no external embedding
  service); pluggable embedding backend behind `[llm]`. Enables "6 months ago
  strategy 23 failed on CPI" recall as retrieved context for the committee.
- **Acceptance:** `query("CPI")` retrieves the CPI-tagged past decision offline.

### WP-7.3 — Meta-Learning Engine  (module 15)
- **Files:** `quantos/meta/base.py` (`RegimePerformanceTable`, `MetaLearner`
  Protocol), `quantos/meta/learner.py` (`BaselineMetaLearner`),
  `tests/test_meta.py`.
- **Build:** `RegimePerformanceTable` accumulates validated performance per
  `(strategy_family, regime)` from the StrategyLab results and the DecisionArchive
  outcomes. `MetaLearner.select(regime, universe)` returns **only** the families
  whose validated stats clear a bar for that regime (empty ⇒ stand down).
  `MetaLearner.update(archive)` refreshes the table from new outcomes (continuous
  learning). Deterministic and explainable: `select` exposes why each family was
  chosen/rejected (I4, I8).
- **Acceptance:** given a seeded table where family A is validated in `TREND_UP`
  and family B in `RANGE`, `select(TREND_UP)` returns A and not B; an unvalidated
  regime returns an empty set (stand down); `update` moves a family in/out of
  validation as outcomes change.

### WP-7.4 — Wire regime → meta-selection into the flow
- **Files:** integrate into the deliberation entry point (a
  `research_pipeline`/orchestrator that composes Regime → MetaLearner → Committee),
  `tests/test_pipeline.py`.
- **Build:** the full ARCHITECTURE §4 flow: classify regime → `MetaLearner.select`
  → selected strategies emit signals into the committee → decision records the
  regime + strategies considered. All offline and reproducible.
- **Acceptance:** for a `TREND_UP` fixture only trend-validated strategies feed
  the committee; for an untradeable/unvalidated regime the pipeline stands down;
  the decision's `as_dict()` shows the regime and the strategies considered (I4).

### WP-7.5 — Continuous audit (the Auditor)
- **Files:** `quantos/learning/audit.py`, `tests/test_audit.py`.
- **Build:** `audit(archive)` that mines closed trades for patterns (which analyst
  was most wrong, which regime hurt, indicator hit-rate) and emits a structured
  report + suggested weight adjustments for the `ConfidenceModel` and validation
  changes for the Meta-Learner.
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
- Reproducibility (I8): research paths are seeded; decisions/backtests replay to
  the same result.

Build M1 first (the Investment Committee), then M2 onward in order.
