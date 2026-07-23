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
pip install -e ".[ml]"        # + scikit-learn, hmmlearn (optional detectors/classifiers)
pip install -e ".[llm]"       # + anthropic, langfuse, langgraph (optional LLM stack)
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

## Market State Intelligence (Milestone 4 — shipped)

The platform now reads the *state* of the market before deciding:

- **Anomaly detector** (`anomaly/`): the `AnomalyDetector` port with a
  dependency-free `ZScoreDetector` baseline — causal per-kind z-scores over
  volume spikes, volatility bursts, price gaps and suspected wash-trading
  (baselines shifted one bar so a spike never hides in its own statistics,
  I2) — plus an optional `IsolationForestDetector` behind lazy `[ml]`.
- **Regime features** (`features/regime_features.py`): no-look-ahead trend
  strength (ADX, EMA slope), realised & ATR volatility, range-vs-trend
  character (Hurst, Kaufman efficiency ratio), volume regime and macro-event
  proximity from the `events` channel — all prefix-invariant (I2).
- **Market Regime Engine** (`regime/`): `RegimeClassifier` port +
  `RegimeState` (label `TREND_UP|TREND_DOWN|RANGE|HIGH_VOL|LOW_VOL|
  MACRO_EVENT|CRISIS`, per-label probabilities, driving features and signed
  `Evidence` explaining the call, I4). The `RuleRegimeClassifier` baseline
  is an explicit, deterministic cascade (I8); `GmmRegimeClassifier` /
  `HmmRegimeClassifier` fit statistical components behind lazy `[ml]` and
  name them via the same rule engine — explainable either way.
- **Regime-aware committee** (`regime_aware_committee()`): deliberations are
  enriched with the classified `regime` + active `anomalies`, an
  `AnomalyAnalyst` surfaces direction-neutral caution, the Chair's **regime
  gate** stands down in an untradeable regime (before the risk veto, which
  stays absolute, I5), and the decision records both (I4).
- **Scenario simulator** (`scenarios/`): `COVID_CRASH`, `FTX`, `ETF_RALLY`,
  `BEAR_2022`, `BULL_2021` as parameterised synthetic generators, each
  labelling its ground-truth regime — the Regime Engine recovers all five on
  their core segments. `simulate(strategy_or_committee, scenario)` returns a
  standard `BacktestResult`: pure research maths, no broker, no capital (I1).

## Strategy Lab (Milestone 5 — shipped)

The platform now *invents* strategies, then validates and culls them:

- **Strategy base + registry** (`strategy/base.py`): the one canonical
  `Strategy`/`SignalStrategy` port (the M4 simulator re-exports it), a
  hashable, versioned `StrategySpec` (`family` + `target_regimes` for the
  M7 Meta-Learner, content-hash identity pinned into every run, I8) and the
  `IndicatorStrategy` compiler turning a spec (indicator blocks + params +
  threshold rules) into causal target positions in [-1, 1] (I2, proven by
  prefix-invariance and future-perturbation tests per block). New blocks
  register without core edits (I7).
- **AI strategy generator** (`strategy/generator.py`): `generate(n, seed,
  diversity)` — a deterministic random/grammar search over five family
  templates (trend, mean-reversion, momentum, breakout, volatility). Every
  spec is validated runnable; batches are unique on content hash *and*
  indicator set and gated on a Jaccard diversity metric. `generate(100)`
  yields 100 unique valid specs, bit-for-bit reproducible per seed (I8).
  An optional LLM backend sits behind the `LLMClient` port (real adapters
  in M6); tests use only the deterministic `MockLLMClient` (I6).
- **Strategy Lab** (`strategy/lab.py`): `StrategyLab.run(specs, ohlcv)`
  backtests every candidate through the M1 engine (M3 cost model
  pluggable) and ranks on a fitness that **folds in the M3
  anti-overfitting statistics** (I9): positive out-of-sample Sharpe is
  deflated by the DSR at `n_trials = batch size`, drawdown is penalised
  and the batch's CSCV PBO is recorded — a data-mined spec with a
  spectacular in-sample Sharpe cannot top the ranking. The weak are
  culled (top-k + DSR floor) and every record, including the **regime the
  batch was tested under**, is upserted to the `Store` for the M7
  Meta-Learner. MLflow logging is lazy and optional.
- **Genetic evolution** (`strategy/evolution.py`): `Genome` encodes a
  spec's params + rule thresholds inside the registry's bounds;
  `Evolver` is a dependency-free elitist GA (tournament selection, blend
  crossover, Gaussian mutation) — mean population fitness provably
  improves across generations, deterministically per seed (I8).
  DEAP/Optuna remain optional accelerators, never required.

## LLM analysts + debate + AI Challenger (Milestone 6 — shipped)

The committee can now think with language models — without ever needing one:

- **LLM access layer** (`llm/client.py`): the one canonical `LLMClient`
  port (the M5 generator re-exports it) and `get_llm_client()`, which
  resolves backends in strict priority order — **Claude** (lazy
  `anthropic`, `ANTHROPIC_API_KEY`) ▸ **OpenRouter** (OpenAI-compatible,
  stdlib HTTP, `OPENROUTER_API_KEY`) ▸ **local Ollama**
  (`QUANTOS_OLLAMA_URL`, default `http://localhost:11434`, **no key
  needed** — the free default) ▸ the deterministic **`MockLLMClient`**
  (offline; the only backend tests use, I6/I8). Keys live only in env,
  never in code or the manifest-pinned `Settings`; Langfuse tracing is
  optional and lazy.
- **LLM analyst** (`committee/llm.py`): `LLMAnalyst(category, client)`
  plugs any backend into the unchanged `Analyst` ABC (I7). The model
  answers a deterministic fact sheet with strict JSON (direction,
  confidence, signed evidence, rationale); on *any* failure — client
  error/timeout, malformed JSON, invalid fields, empty evidence,
  sub-floor confidence, or model self-abstention — the analyst **abstains
  honestly** with the reason recorded (I3/I4). `llm_bench(client)` builds
  a full five-category LLM bench.
- **Debate orchestrator** (`committee/debate.py`): `DebateCommittee` — an
  alternative orchestrator where every analyst opines, sees a compact
  peer summary, and may revise **once** before the Chair decides via the
  unchanged hierarchy (regime gate ▶ absolute risk veto, I5 ▶ threshold).
  The full debate (first round, revisions) is pinned into the decision's
  `run_manifest` and surfaced in `explain_decision` (I4). Plain-Python
  loop by default; LangGraph optional and lazily imported.
- **AI Challenger** (`committee/challenger.py`, module 17): the official
  devil's advocate. The deterministic `RuleChallenger` builds the case
  against an approved call from the committee's own opposing evidence,
  fresh stretch statistics (z-score over-extension, RSI extreme, elevated
  vol) and a contradicting regime; the optional `LLMChallenger` fails
  **safe** (agrees) on any malformed output. A material objection forces
  exactly **one** extra deliberation round, and the decision records the
  challenge, the provisional call, and whether the objection was decisive
  (I4). The Challenger has **no veto** — it can neither impose nor rescue
  one; that power stays the Risk Manager's alone (I5).

## Memory & Learning (Milestone 7 — shipped)

The loop is closed — every decision is remembered, scored, and learned from:

- **Decision Archive** (`memory/archive.py`): every decision's full dossier
  (regime, strategies, evidence, run manifest) persists to the Store under a
  content-addressed id — idempotent recording, bit-for-bit replay (I8) —
  and is later closed with its realised outcome. Queryable by symbol,
  window, regime and state; `closed()` is the learning corpus.
- **RAG memory** (`memory/rag.py`): the `MemoryStore` port with an in-house
  TF-IDF retriever (numpy only, deterministic) over archived episodes —
  `query("CPI")` recalls the past CPI failure with its regime and outcome
  attached; a pluggable `embedder` swaps in vector search.
- **Meta-Learning Engine** (`meta/`, module 15): the `RegimePerformanceTable`
  accumulates validated evidence per (strategy family, regime) from Strategy
  Lab survivors and closed outcomes; `BaselineMetaLearner.select` admits
  **only regime-validated families** with a per-family verdict (I4), stands
  down when none qualify, and `update()` moves families in and out of
  validation as outcomes change.
- **Research pipeline** (`pipeline.py`): the full ARCHITECTURE §4 flow in one
  call — classify regime → meta-select → selected strategies emit signals →
  committee deliberates; the decision records regime, strategies considered
  and verdicts. Untradeable regime → Chair's gate; no validated family →
  meta gate, verdicts in the reasons.
- **The Auditor** (`learning/audit.py`): scores every non-abstained opinion
  against realised outcomes (abstention is never punished, I3), breaks pnl
  down by regime and family, and emits **proposals** — lower a persistently
  wrong analyst's weight, revoke a dying family's validation — never
  auto-applied (§4.1).
- **Confidence Calibration** (`committee/calibration.py`, module 18): a
  binned, monotone, regime-aware stated-vs-realised map — "90%" that wins
  60% calibrates to ~0.60; identity until history exists. The drop-in
  `CalibratedConfidenceModel` re-applies the threshold on calibrated
  confidence with zero core edits (I7).
- **Experiment Registry** (`research/experiments.py`, module 19): the
  scientific-lab ledger — hypothesis → pinned setup → result → conclusion,
  content-addressed, idempotent, immutable once completed, replayable (I8).

## Presentation & Delivery (Milestone 8 — shipped)

The platform now shows its work and speaks for itself:

- **Dashboard** (`dashboard/`): `panels.py` builds every view as plain
  data — equity and drawdown as separate single-series frames, metric
  tiles, open positions, the decision narrative (`explain_decision`),
  regime history, calibration reliability, news and Strategy-Lab results —
  fully testable offline (I6). `app.py` is a thin Streamlit shell behind
  the `[dashboard]` extra, imported lazily; nothing in quantos ever
  requires it. Launch the app with one command — `quantos-app` — after
  `pip install -e '.[dashboard]'`; it runs a full seeded pass out of the
  box (no lake to populate first). See `SETUP.md` for real data + LLM setup.
- **Observability** (`obs/`): `ExperimentLogger` records runs
  (params/metrics/tags) through MLflow when the `[obs]` extra exists and
  through an identical deterministic local-JSON store otherwise (I8);
  `metrics.py` is an in-house Counter/Gauge registry that renders standard
  Prometheus text exposition with zero dependencies.
- **Hermes** (`hermes/`, module 24): the read-only communications agent.
  Outbound, `Notifier` routes `HermesEvent`s (decision, veto,
  regime_change, anomaly, digest, hypothesis) per kind with content-hash
  dedupe and a sliding-window rate limit on an injectable clock;
  `ConsoleChannel` is the offline default and Telegram/Discord/Email
  adapters read their tokens **only** from env. Alert bodies are the
  decision's already-recorded explanation (I4). Inbound, `answer()`
  retrieves archived episodes via the TF-IDF memory and reports what the
  record says — optional LLM phrasing falls back to the deterministic
  template, and a guard test proves the package has **no execution path**
  (I1): Hermes informs, it never trades.

## Advanced Intelligence & Self-Improvement (Milestone 9 — shipped)

The slow, periodic loop that keeps the platform healthy and pushes it to
learn. Every module here **only proposes** — it never auto-applies a
structural change — stays paper-only (I1) and reproducible (I8):

- **Knowledge Engine** (`knowledge/`, module 16): a weighted,
  provenance-carrying relationship graph built from news/on-chain/macro. A
  deterministic lexicon + co-occurrence baseline turns events into edges
  (`ETF ▸ inflows ▸ BTC ▸ rally ▸ bull_regime`); `infer()` surfaces
  implicit relations, `paths()`/`explain()` hand the committee an
  explainable chain. Optional `[llm]` triple extraction degrades to silence
  on any failure (I3).
- **Portfolio Intelligence** (`portfolio/`, module 22): the whole-book
  view — point-in-time cross-asset correlations, net/gross and per-cluster
  exposures, Herfindahl concentration. `PortfolioConcentration` is a drop-in
  `RiskRule` (I7) whose concentration/crowding flag the Risk Manager
  consumes as an absolute veto (I5).
- **Meta-Risk** (`risk/meta.py`, module 23): audits the Risk Manager itself
  from history — the counterfactual win rate of *blocked* setups
  (over-blocking) and loss rate of *allowed* ones (too permissive), per
  regime — and proposes relaxing/tightening limits without ever changing
  one.
- **Self-Evaluation** (`learning/self_eval.py`, module 20): an
  earlier-vs-recent review that ranks which analysts and signals/indicators
  are decaying, scored honestly (abstentions never counted, I3); an optional
  health snapshot flags stale datasets.
- **Hypothesis Generator** (`research/hypotheses.py`, module 23): distils
  Self-Evaluation, the Auditor and the Knowledge Engine into ranked,
  plain-language research questions and registers each as an immutable
  `Experiment` — closing the research cycle. Deterministic baseline; optional
  LLM ideation.
- **Market Simulator** (`sim/`, module 21): replays a scenario
  (`COVID_CRASH`, `FTX`, `ETF_RALLY`, …) **bar-by-bar as if live** through
  the full pipeline (regime → meta → committee → paper), so the system can
  be watched reacting in real time. Each step sees only bars ≤ t (no
  look-ahead, I2), every fill is paper (no capital, I1); a pure function of
  `(scenario, seed)` (I8).

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
├── features/                causal technical indicators + regime features (M4)
├── llm/                     LLMClient port + Claude/OpenRouter/Ollama/Mock
│                            backends, lazy Langfuse tracing (M6)
├── committee/               analysts (incl. AnomalyAnalyst + LLMAnalyst), confidence
│                            model, risk veto, chair, decision (regime + anomalies,
│                            I4), debate orchestrator + AI Challenger (M6)
├── anomaly/                 AnomalyDetector port; ZScoreDetector baseline,
│                            IsolationForest (lazy [ml]) (M4)
├── regime/                  Market Regime Engine: RegimeState + rule classifier,
│                            GMM/HMM (lazy [ml]) (M4)
├── scenarios/               named scenario library + simulator (paper only) (M4)
├── sim/                      MarketSimulator: bar-by-bar real-time replay (M9)
├── strategy/                Strategy Lab (M5): spec + block registry + compiler,
│                            deterministic/LLM generator, DSR/PBO-honest lab,
│                            dependency-free genetic evolution
├── risk/                    composable risk limit library (M3); Meta-Risk (M9)
├── knowledge/               KnowledgeGraph + KnowledgeEngine (M9)
├── portfolio/               PortfolioAnalyzer: correlations/exposure/concentration (M9)
├── explain/                 explain_decision / decision_report (regime + anomaly
│                            sections)
├── backtest/                engine (lagged positions), walk-forward (+DSR), Monte
│                            Carlo, forward test, anti-overfitting statistics
│                            (DSR/PBO/CPCV), buy-and-hold + random baselines
├── paper/                   PaperBroker + per-trade dossier (TradeRecord)
├── execution/               Broker/RiskGate/ExecutionEngine ports; CostModel fills;
│                            live HARD-DISABLED
├── sizing/                  PositionSizer port + VolTarget/Kelly/RiskParity (M3)
├── memory/                  Decision Archive (dossiers + outcomes) + MemoryStore
│                            port + TF-IDF RAG recall (M7)
├── meta/                    Meta-Learning Engine: regime x family performance
│                            table + gated selection (M7)
├── learning/                the Auditor (M7) + Self-Evaluation (M9): propose-only
├── research/                Experiment Registry (M7) + Hypothesis Generator (M9)
├── pipeline.py              ResearchPipeline: regime -> meta -> committee (§4, M7)
├── dashboard/               UI-free panel builders + lazy Streamlit app (M8)
├── obs/                     ExperimentLogger (MLflow or local-JSON) + Prometheus-
│                            text metrics registry (M8)
├── hermes/                  read-only comms agent: events, Notifier, channels (M8)
└── cli.py                   decide | backtest | walkforward | montecarlo | paper |
                             ingest | catalog | health
```

## Tests

```bash
cd quant && python -m pytest        # offline, deterministic, fast
```

## Status

Milestones 1 (Investment Committee), 2 (Data Infrastructure), 3
(Validation rigor: risk limits, forward test, anti-overfitting statistics,
execution realism, position sizing), 4 (Market State Intelligence:
anomaly detection, regime features, Market Regime Engine, regime-aware
committee, scenario simulator), 5 (Strategy Lab: strategy spec +
registry, AI strategy generator, DSR/PBO-honest lab ranking + cull,
genetic evolution), 6 (LLM analysts: canonical LLMClient port with
Claude ▸ OpenRouter ▸ Ollama ▸ Mock resolution, honest-abstention
LLMAnalyst, debate orchestrator, AI Challenger), 7 (Memory & Learning:
Decision Archive, RAG memory, Meta-Learning Engine, research pipeline,
Auditor, Confidence Calibration, Experiment Registry), 8 (Presentation
& Delivery: offline dashboard panels + lazy Streamlit app, experiment
logging + metrics, the read-only Hermes communications agent) and 9
(Advanced Intelligence & Self-Improvement: Knowledge Engine, Portfolio
Intelligence, Meta-Risk, Self-Evaluation, Hypothesis Generator, real-time
replay simulator) are complete.

**All nine milestones are shipped** — the ARCHITECTURE is realised end to
end. Remaining work hardens and tunes the platform (threshold calibration
on real data, CI relocation) rather than adding milestones.
