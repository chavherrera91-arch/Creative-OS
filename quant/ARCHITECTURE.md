# quantos — Architecture (master design)

> **Role split.** This document is written by the *architect* (Opus). It is the
> single source of truth for **what** the system is and **why**. The companion
> [`BUILD_PLAN.md`](./BUILD_PLAN.md) tells the *builder* (Fable 5) **how** to
> construct it, in independently-shippable work packages. **No implementation
> exists yet** — this branch is the architecture; Fable builds from Milestone 1.

---

## 0. North star

`quantos` is an **AI quant research platform**, not a trading bot. It researches
markets, forms an evidence-based opinion through a multi-agent **Investment
Committee**, validates every idea through a rigorous backtest → walk-forward →
Monte Carlo → forward-test → paper-trading funnel, and **only paper-trades**.
Real order routing is designed for but hard-disabled.

Two ideas make it more than a bot:

1. It does not hunt for a single winning strategy. A **Market Regime Engine**
   classifies the current market state (trend, range, high/low volatility, macro
   event, crisis…) and a **Meta-Learning Engine** selects only the strategy
   families **previously validated for that regime**. The right question is never
   "what's the best strategy?" but "what works *now*, given this regime?"
2. Every decision is **explainable, auditable and reproducible**: you can replay
   any decision, see which agent contributed which evidence under which regime,
   and fix that component instead of the whole system.

The value compounds in three hard-to-replicate assets: the **Data Lake** (months
of tagged market/derivatives/on-chain/macro/sentiment/news data), the **decision
archive** (every decision + outcome), and the **regime→strategy performance map**
the Meta-Learner accumulates.

### Non-negotiable invariants

These hold in **every** milestone. A change that violates any of them is wrong by
definition.

| # | Invariant | Enforced by |
| - | --------- | ----------- |
| I1 | **No real capital.** No code path places a live order. | `execution.build_execution_engine` raises `LiveExecutionDisabled`; only `is_paper` brokers accept orders. |
| I2 | **No look-ahead.** A value at bar *t* uses only data with `event_time ≤ t`; positions are lagged before P&L; feature reads are as-of. | `backtest.engine`, indicators, `FeatureStore.as_of`. |
| I3 | **Honest abstention.** An analyst with no data abstains; it never fabricates conviction. | `Analyst._abstain`, `abstained` excluded from aggregation. |
| I4 | **Auditability.** Every decision serialises to a complete record (regime, strategies considered, analysts, evidence, confidence, risk). | `CommitteeDecision.as_dict()`, `DecisionArchive`. |
| I5 | **Risk veto is absolute.** One veto blocks the trade regardless of confidence. | `Chair.decide`. |
| I6 | **Runs offline, no secrets.** Every module has a deterministic offline path; keys are never required for research. | synthetic fallbacks, `.env.example`. |
| I7 | **Interfaces before implementations.** New capabilities plug into existing Protocols without refactoring the core. | `Analyst`, `Broker`, `RiskGate`, `ExecutionEngine`, `DataSource`/`Connector`, `Strategy`, `RegimeClassifier`, `MetaLearner`. |
| I8 | **Reproducibility.** Any decision or backtest can be replayed to the same result: seeds are fixed, and data/schema/strategy/model artifacts are versioned and pinned in the record. | seed plumbing, `SchemaRegistry`, `StrategySpec.version`, run manifests. |
| I9 | **Statistical honesty.** No single-split backtest is ever presented as evidence on its own. Every reported edge is corrected for multiple testing and validated with purged, embargoed out-of-sample CV; a Deflated Sharpe Ratio / PBO accompanies any strategy that ships. | `backtest.validation` (deflated Sharpe, PBO, CPCV), Strategy Lab ranking (module 25). |

---

## 1. Current state

**Milestone 1 (Investment Committee) is shipped** — WP-0 and WP-1.1→1.8 are
implemented under `quant/quantos/` with a green, offline, deterministic test
suite (`cd quant && python -m pytest`): core types, causal indicators, five
specialist analysts, confidence aggregation, risk veto, chair, explainability,
the backtest→walk-forward→Monte Carlo funnel with mandatory baselines, paper
trading, hard-disabled live execution, and the CLI
(`python -m quantos.cli decide|backtest|walkforward|montecarlo|paper`).

**Milestone 2 (Data Infrastructure) is shipped** — WP-2.1→2.9 per
[`docs/DATA_INFRASTRUCTURE.md`](./docs/DATA_INFRASTRUCTURE.md): versioned
schemas + migrations + validation, the tiered `Store` (DuckDB/Parquet default,
lazy Timescale), the self-registering `Connector` framework (zero core edits
per source, I7), six connectors (market, derivatives, on-chain, macro,
sentiment, news — all with deterministic synthetic modes), resilient
idempotent ingestion (retry, circuit breaker, watermarks), gap repair, the
offline-testable scheduler, the health monitor, the catalog, the
point-in-time `FeatureStore` (I2), the `DataLake` facade whose snapshots let
the committee deliberate with **0 abstentions**, the lake CLI
(`ingest|catalog|health|decide --from-lake`) and the optional
`docker-compose.yml` infra (no secrets).

**Milestone 3 (Validation rigor) is shipped** — WP-3.1→3.5: the composable
risk limit library (`risk.limits`: `VolatilitySpike`, `MacroEvent`,
`DailyDrawdown`, `LowLiquidity`, `CorrelationBreak`, `MaxPositionSize`;
`RiskManager` runs a configurable rule list back-compatibly, one veto still
absolute, I5), the forward test (`backtest.forward`: bar-by-bar
committee→paper bridge, I1/I2), the anti-overfitting statistics
(`backtest.validation`: Deflated Sharpe Ratio with an in-house normal
CDF/PPF, CSCV-based PBO, `CombinatorialPurgedCV` with purge + embargo;
`walk_forward` now attaches a DSR report to every OOS result, I9), execution
realism (`execution.costs`: `CostModel` with fee + size-dependent slippage +
square-root market impact, regime/liquidity aware, routed through
`PaperBroker` and `backtest`, flat/zero models back-compatible) and position
sizing (`sizing`: `VolTargetSizer`, `FractionalKellySizer`,
`RiskParitySizer`, all bounded by the Risk Manager's limits and consulted by
the paper executor, I5).

**Milestone 4 (Market State Intelligence) is shipped** — WP-4.1→4.5: the
anomaly detector (`anomaly`: `AnomalyDetector` port, dependency-free
`ZScoreDetector` over volume spikes / volatility bursts / gaps / suspected
wash-trading with one-bar-shifted causal baselines, lazy
`IsolationForestDetector` behind `[ml]`), the regime feature set
(`features.regime_features`: ADX, EMA slope, Hurst, efficiency ratio,
realised/ATR vol, volume regime, macro-event proximity — all
prefix-invariant, I2), the Market Regime Engine (`regime`: `RegimeState`
with probabilities + driving features + signed `Evidence`, the
deterministic `RuleRegimeClassifier` cascade, lazy GMM/HMM backends whose
learned components are named by the same rule engine), the regime-aware
committee (`regime_aware_committee()`: context enriched with `regime` +
`anomalies`, `AnomalyAnalyst` direction-neutral caution, the Chair's
regime gate standing down in untradeable regimes ahead of the still-absolute
risk veto, both recorded in the decision and in `explain_decision`, I4/I5)
and the scenario simulator (`scenarios`: `COVID_CRASH`, `FTX`, `ETF_RALLY`,
`BEAR_2022`, `BULL_2021` as seeded synthetic generators labelling their
ground-truth regime — all five recovered by the classifier —
`simulate(strategy_or_committee, scenario) -> BacktestResult`, paper maths
only, I1).

**Milestone 5 (Strategy Lab) is shipped** — WP-5.1→5.4: the strategy base
(`strategy.base`: the **one canonical** `Strategy`/`SignalStrategy` port —
the M4 simulator now re-exports it — a frozen, content-hashed, versioned
`StrategySpec` with `family` + `target_regimes`, the `IndicatorStrategy`
compiler from spec to causal target positions in [-1, 1] with
prefix-invariance/future-perturbation tests per block, I2/I8, and the
building-block registry: 10 causal indicator blocks + 5 comparators, new
blocks pluggable without core edits, I7), the AI strategy generator
(`strategy.generator`: deterministic random/grammar search over five family
templates as the offline default — `generate(100)` yields 100 unique valid
specs per seed, unique on content hash *and* indicator set, gated on a
Jaccard diversity metric — plus an optional LLM backend behind the
`LLMClient` port exercised only via the deterministic `MockLLMClient`), the
Strategy Lab (`strategy.lab`: auto-backtest through the M1 engine with the
M3 cost model pluggable, fitness = DSR-deflated OOS Sharpe at
`n_trials = batch size` with a drawdown penalty and the batch CSCV PBO
recorded, so a data-mined spec cannot top the ranking, I9; top-k cull with
a DSR floor; results + the **tested regime** upserted to the `Store` for
the M7 Meta-Learner; lazy optional MLflow) and genetic evolution
(`strategy.evolution`: `Genome` encoding a spec's params + rule thresholds
inside registry bounds, a dependency-free elitist GA — tournament
selection, blend crossover, Gaussian mutation — whose mean population
fitness provably improves across generations, deterministic per seed, I8;
DEAP/Optuna optional, never required).

**Milestone 6 (LLM analysts + debate + AI Challenger) is shipped** —
WP-6.1→6.4: the **one canonical** `LLMClient` port (`quantos.llm.client`;
the M5 generator re-exports it — no forked ports, I7) whose
`get_llm_client` factory resolves backends in strict priority order —
Claude (lazy `anthropic`, `ANTHROPIC_API_KEY`) ▸ OpenRouter (stdlib HTTP,
`OPENROUTER_API_KEY`) ▸ local Ollama (`QUANTOS_OLLAMA_URL`, **no key
needed** — the free default) ▸ the deterministic `MockLLMClient` (offline,
the only backend tests use, I6/I8), keys only via env and never inside the
manifest-pinned `Settings`, with optional lazy Langfuse tracing; the
`LLMAnalyst` (`committee.llm`) plugging any backend into the unchanged
`Analyst` ABC (I7) and abstaining honestly on *any* failure — client
error/timeout, malformed JSON, out-of-range fields, empty evidence,
sub-floor confidence, or model self-abstention (I3), with the parsed
opinion carrying real signed `Evidence` (I4); the debate protocol
(`committee.debate`): `DebateCommittee`, an alternative orchestrator where
every analyst sees a peer summary and may revise **once** before the Chair
applies the unchanged hierarchy (regime gate ▶ absolute risk veto, I5 ▶
threshold), the full debate pinned into the decision's `run_manifest` and
surfaced in `explain_decision` (I4), plain-Python loop by default and
LangGraph optional/lazy; and the **AI Challenger** (module 17,
`committee.challenger`): the `Challenger` port with the deterministic
`RuleChallenger` (counter-case from the committee's own opposing evidence,
fresh stretch statistics and a contradicting regime) and the fail-safe
`LLMChallenger` — a material objection triggers exactly one extra
deliberation round and the decision records the challenge, the provisional
call and whether the objection was decisive (I4); the Challenger holds
**no veto** and can neither impose nor rescue one (I5).

**Milestone 7 (Memory & Learning) is shipped** — WP-7.1→7.7: the Decision
Archive (`memory.archive`: content-addressed dossiers + realised outcomes
over the Store, queryable by symbol/window/regime, replayable from the
pinned manifest, I4/I8), RAG memory (`memory.rag`: `MemoryStore` port with
an in-house TF-IDF retriever — `query("CPI")` recalls the past CPI failure
with regime and outcome attached; pluggable embedder), the Meta-Learning
Engine (`meta`: `RegimePerformanceTable` fed by Strategy Lab survivors and
closed outcomes; `BaselineMetaLearner.select` admits only regime-validated
families with per-family verdicts, stand-down when none, continuous
`update`), the research pipeline (`pipeline.ResearchPipeline`: the full §4
flow — classify regime → meta-select → selected strategies emit signals →
committee; Chair's gate for untradeable regimes, meta gate with recorded
verdicts for unvalidated ones), the Auditor (`learning.audit`: scores every
non-abstained opinion against outcomes, finds the weakest analyst and dying
families, emits propose-never-apply adjustments, §4.1), Confidence
Calibration (`committee.calibration`: binned regime-aware stated-vs-realised
map, cold-start identity, drop-in `CalibratedConfidenceModel`, I7) and the
Experiment Registry (`research.experiments`: immutable
hypothesis→result→conclusion ledger, content-addressed and replayable, I8).

Fable 5 continues milestone by milestone from **M8 — Presentation &
Delivery**, each work package shipping with tests and preserving every
invariant in §0.

---

## 2. Target architecture

### 2.1 Layered view

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION      Dashboard (Streamlit)  ·  CLI  ·  REST API (opt)    │
│                    Hermes — comms agent (push alerts + conversational)  │
├──────────────────────────────────────────────────────────────────────┤
│  ORCHESTRATION     RegimeClassifier → MetaLearner.select →             │
│                    InvestmentCommittee  ·  StrategyLab  ·  Scheduler   │
│                    (LangGraph optional for agent debate)              │
├──────────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE      Analysts (rule + LLM)  ·  Confidence + Calibration  │
│                    Risk + Meta-Risk  ·  AI Challenger                   │
│                    Anomaly detector  ·  Market Regime Engine           │
│                    Strategy generator + GA  ·  Meta-Learning Engine    │
│                    Knowledge Engine  ·  Portfolio Intelligence         │
│                    Memory (RAG)  ·  Scenario/Market Simulator          │
│  SELF-IMPROVEMENT  Experiment Registry · Self-Evaluation · Hypothesis  │
│                    Generator  → feeds new experiments back in (§4.1)   │
├──────────────────────────────────────────────────────────────────────┤
│  RESEARCH          Backtest · Walk-forward · Monte Carlo · Forward ·   │
│                    Paper trading                                       │
├──────────────────────────────────────────────────────────────────────┤
│  DATA LAKE         Connectors → TimescaleDB (hot) + DuckDB/Parquet     │
│                    market · derivatives · on-chain · macro · sentiment │
│                    · news (AI-tagged)          Redis (cache/bus)       │
├──────────────────────────────────────────────────────────────────────┤
│  EXECUTION         Broker / RiskGate / ExecutionEngine  (PAPER ONLY)   │
├──────────────────────────────────────────────────────────────────────┤
│  OBSERVABILITY     MLflow (experiments) · Langfuse (LLM) · Prometheus  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 The modules → concrete packages

| Vision module | Package(s) | Milestone | Key contract |
| ------------- | ---------- | --------- | ------------ |
| 1. Data Lake | `data.schema`, `data.store`, `data.connectors`, `data.ingest`, `data.quality`, `data.catalog`, `data.lake`, `data.featurestore` | **M2 ✅ shipped** | `Connector`, `Store`, `Schema` |
| 2. Multi-agent engine | `committee/*`, `committee.llm`, `committee.debate`, `llm.client` | **M1 + M6 ✅ shipped** | `Analyst`, `Chair`, `LLMClient` |
| 3. Confidence system | `committee.confidence` | **M1 ✅ shipped** | `ConfidenceModel` |
| 4. Anomaly detector | `anomaly` | **M4 ✅ shipped** | `AnomalyDetector` |
| 5. Strategy generator | `strategy.generator`, `strategy.lab` | **M5 ✅ shipped** | `Strategy`, `StrategySpec` |
| 6. Genetic evolution | `strategy.evolution` | **M5 ✅ shipped** | `Genome`, `Evolver` |
| 7. Pro backtesting | `backtest/*` (incl. forward test) | **M1 + M3 ✅ shipped** | `BacktestResult` |
| 8. Risk engine | `committee.risk_manager`, `risk.limits` | **M1 + M3 ✅ shipped** | `RiskManager` |
| 9. Explainable AI | `explain/*` | **M1 ✅ shipped** | `explain_decision` |
| 10. Continuous learning | `memory.archive`, `learning.audit` | **M7 ✅ shipped** | `DecisionArchive` |
| 11. Dashboard | `dashboard/` (Streamlit) | M8 | reads Store + Archive |
| 12. Memory (RAG) | `memory.rag` | **M7 ✅ shipped** | `MemoryStore` |
| 13. Scenario simulator | `scenarios` | **M4 ✅ shipped** | `Scenario` |
| **14. Market Regime Engine** | `regime` | **M4 ✅ shipped** | `RegimeClassifier`, `RegimeState` |
| **15. Meta-Learning Engine** | `meta` | **M7 ✅ shipped** | `MetaLearner`, `RegimePerformanceTable` |
| **16. Knowledge Engine** | `knowledge` | **M9** | `KnowledgeGraph`, `KnowledgeEngine` |
| **17. AI Challenger** | `committee.challenger` | **M6 ✅ shipped** | `Challenger` |
| **18. Confidence Calibration** | `committee.calibration` | **M7 ✅ shipped** | `ConfidenceCalibrator` |
| **19. Experiment Registry** | `research.experiments` | **M7 ✅ shipped** | `Experiment`, `ExperimentRegistry` |
| **20. Self-Evaluation** | `learning.self_eval` | **M9** | `SelfEvaluator` |
| **21. Market Simulator** (real-time replay) | `scenarios.simulator` (extend), `sim` | **M4 ✅ shipped** / M9 replay | `MarketSimulator` |
| **22. Portfolio Intelligence** | `portfolio` | **M9** | `PortfolioAnalyzer` |
| **23. Meta-Risk + Hypothesis Gen** | `risk.meta`, `research.hypotheses` | **M9** | `MetaRisk`, `HypothesisGenerator` |
| **24. Hermes — Communications Agent** | `hermes` | **M8** | `Notifier`, `Channel`, `HermesAgent` |
| **25. Statistical Validation** (anti-overfitting) | `backtest.validation` | **M3 ✅ shipped** | `deflated_sharpe`, `pbo`, `CombinatorialPurgedCV` |
| **26. Execution Realism + Position Sizing** | `execution.costs`, `sizing` | **M3 ✅ shipped** | `CostModel`, `PositionSizer` |

### 2.3 Core contracts (the spine every module builds on)

```python
# data/models.py
MarketSnapshot(symbol, timeframe, ohlcv, derivatives, onchain, macro,
               sentiment, events, news)   # analysts read whatever is present

# committee/base.py
Direction(LONG|FLAT|SHORT)
Evidence(name, detail, impact:[-1,1], value)     # signed, auditable
AnalystOpinion(analyst, category, direction, confidence:[0,1], evidence, abstained)
class Analyst(ABC): def analyze(snapshot, context) -> AnalystOpinion

# committee/decision.py — the auditable, reproducible record
CommitteeDecision(symbol, timeframe, price, direction, approved, confidence,
                  blocked_by_risk, reasons, opinions, confidence_report, risk,
                  regime, strategies_considered, run_manifest)

# execution/interfaces.py  (Protocols — new engines must satisfy these)
Broker(is_paper, submit, equity)
RiskGate(allow(decision) -> bool)
ExecutionEngine(execute(decision, price))
```

### 2.4 New contracts introduced by later milestones

```python
# data/connectors/base.py  (M2) — every data source is a plug-in
class Connector(ABC):
    metadata: ConnectorMetadata
    def fetch(self, req: FetchRequest) -> FetchResult: ...
    def synthetic(self, req: FetchRequest) -> FetchResult: ...   # offline (I6)
    def healthcheck(self) -> HealthStatus: ...

# data/store.py (M2) — tiered persistence (Timescale prod, DuckDB/Parquet offline)
class Store(Protocol):
    def write(self, tier, table, df) -> int: ...
    def upsert(self, tier, table, df, keys) -> int: ...          # idempotent
    def read(self, tier, table, symbol=None, start=None, end=None) -> DataFrame: ...

# data/featurestore.py (M2) — point-in-time correct reads (I2)
class FeatureStore:
    def as_of(self, symbol, at, features) -> dict: ...           # never event_time > at

# anomaly/base.py (M4)
class AnomalyDetector(Protocol):
    def fit(self, df): ...
    def score(self, df) -> Series: ...          # higher = more anomalous
    def flags(self, df) -> Series[bool]: ...

# regime/base.py (M4) — classify the market state
class RegimeState:                              # explainable classification
    label: str                                  # TREND_UP|TREND_DOWN|RANGE|HIGH_VOL|LOW_VOL|MACRO_EVENT|CRISIS
    probabilities: dict[str, float]
    features: dict[str, float]                  # ADX, realised vol, Hurst, event flags…
    evidence: list[Evidence]
class RegimeClassifier(Protocol):
    def classify(self, snapshot: MarketSnapshot) -> RegimeState: ...

# strategy/base.py (M5)
@dataclass
class StrategySpec: name; version; params: dict; indicators: list[str]; rationale: str
class Strategy(Protocol):
    spec: StrategySpec
    def signals(self, ohlcv) -> Series[float]   # target position -1..1, no look-ahead

# meta/base.py (M7) — learn which strategy FAMILIES work in which REGIME
class RegimePerformanceTable:                   # (family, regime) -> validated stats
    def record(self, family, regime, metrics): ...
    def validated(self, regime, bar) -> list[str]: ...   # families cleared for a regime
class MetaLearner(Protocol):
    def select(self, regime: RegimeState, universe: list[Strategy]) -> list[Strategy]: ...
    def update(self, archive) -> None: ...      # continuous learning from outcomes

# memory/base.py (M7)
class MemoryStore(Protocol):
    def add(self, doc: dict) -> str: ...
    def query(self, text, k=5, filters=None) -> list[dict]: ...

# committee/challenger.py (M6) — the official devil's advocate (module 17)
class Challenger(Protocol):
    def contest(self, decision: CommitteeDecision, snapshot) -> ChallengeResult: ...
    # ChallengeResult: agrees | disputes + counter-evidence -> triggers a re-debate

# committee/calibration.py (M7) — is the stated confidence honest? (module 18)
class ConfidenceCalibrator(Protocol):
    def fit(self, archive) -> "ConfidenceCalibrator": ...   # learn from outcomes
    def calibrate(self, raw_confidence: float, context: dict) -> float: ...  # -> calibrated
    def reliability(self) -> dict: ...                      # bins: stated vs realised

# research/experiments.py (M7) — the scientific-lab ledger (module 19)
@dataclass
class Experiment: id; hypothesis; setup: dict; result: dict; conclusion: str; status
class ExperimentRegistry(Protocol):
    def register(self, hypothesis: str, setup: dict) -> str: ...
    def complete(self, id: str, result: dict, conclusion: str) -> None: ...
    def query(self, **filters) -> list[Experiment]: ...

# knowledge/base.py (M9) — knowledge, not just data (module 16)
class KnowledgeGraph(Protocol):
    def upsert_relation(self, src, rel, dst, weight, provenance): ...
    def neighbours(self, entity, rel=None) -> list: ...
    def paths(self, src, dst, max_len=4) -> list: ...       # e.g. ETF→BlackRock→news→rally
class KnowledgeEngine(Protocol):
    def ingest(self, news, onchain, macro) -> None: ...     # build edges from the lake
    def infer(self, entity) -> list["Relation"]: ...        # surface implicit relations

# portfolio/base.py (M9) — reason about the whole book (module 22)
class PortfolioAnalyzer(Protocol):
    def correlations(self, symbols, window) -> "DataFrame": ...
    def exposures(self, positions) -> dict: ...             # net/gross, factor, cluster
    def concentration(self, positions) -> dict: ...         # limits feed the RiskManager

# risk/meta.py (M9) — a Risk Manager for the Risk Manager (module 23)
class MetaRisk(Protocol):
    def review(self, archive, risk_history) -> MetaRiskReport: ...
    # flags: too conservative? over-blocking? limits stale vs regime shift?

# research/hypotheses.py (M9) — auto-generate the next questions (module 23)
class HypothesisGenerator(Protocol):
    def generate(self, archive, knowledge, self_eval) -> list["Hypothesis"]: ...
    # e.g. "which indicators lost predictive power?" -> Experiments -> research cycle

# learning/self_eval.py (M9) — periodic system health review (module 20)
class SelfEvaluator(Protocol):
    def evaluate(self, archive, meta, health) -> SelfEvalReport: ...
    # which modules/datasets/indicators/agents are decaying?

# hermes/base.py (M8) — the messenger: outbound push + inbound queries (module 24)
class Channel(Protocol):                        # Telegram/Discord/email/console
    name: str
    def send(self, message: str, attachments=None) -> None: ...
    def poll(self) -> list["InboundMessage"]: ...   # optional (conversational)
class Notifier(Protocol):
    def notify(self, event: "HermesEvent", channels=None) -> None: ...
class HermesAgent(Protocol):
    # STRICTLY read-only: informs and answers; never places an order or changes
    # a limit (I1). Answers by querying DecisionArchive/Knowledge/RAG, using the
    # existing explanation — it does not invent new analysis.
    def on_event(self, event: "HermesEvent") -> None: ...   # decision/veto/regime/anomaly/digest
    def answer(self, question: str) -> str: ...             # NL query over the archive

# backtest/validation.py (M3) — anti-overfitting statistics (module 25, I9)
def deflated_sharpe(sharpe, n_trials, skew, kurtosis, n_obs) -> float: ...  # DSR
def pbo(is_returns, oos_returns) -> float: ...              # Prob. of Backtest Overfitting
class CombinatorialPurgedCV:                                # CPCV with purge + embargo
    def split(self, X, label_times, embargo): ...           # no leakage across folds

# execution/costs.py (M3) — realistic fills (module 26)
class CostModel(Protocol):
    def fill(self, side, qty, price, book=None, regime=None) -> "Fill": ...
    # fee + size-dependent slippage + market impact (+ latency/queue for L2)

# sizing/base.py (M3) — how MUCH, not just direction (module 26)
class PositionSizer(Protocol):
    def size(self, decision, portfolio, vol, corr) -> float: ...
    # vol-targeting | fractional-Kelly | risk-parity; bounded by RiskManager limits
```

Everything is designed so an **LLM-backed analyst**, a **live broker**, a **new
data source**, a **generated strategy**, a **new regime classifier** or a
**meta-learning policy** slots in without touching the committee (I7).

---

## 3. Agent roles & orchestration

The multi-agent engine mirrors how a discretionary fund's investment committee
works. Each agent is a self-contained unit with one job; they are composed by the
orchestrator, not hard-wired to each other.

| Agent | Package | Role | Output |
| ----- | ------- | ---- | ------ |
| **Chair / President** (the "CEO") | `committee.chair` | Synthesises all inputs, applies the decision hierarchy, renders the final call. | `CommitteeDecision` |
| Technical Analyst | `committee.analysts` | Trend/momentum/mean-reversion from OHLCV + order-flow. | `AnalystOpinion` |
| Fundamental Analyst | `committee.analysts` | Derivatives structure (funding, OI, basis, L/S). | `AnalystOpinion` |
| Macro Analyst | `committee.analysts` | DXY, rates, CPI/PPI/NFP, FOMC regime. | `AnalystOpinion` |
| Sentiment Analyst | `committee.analysts` | Social + news sentiment, crowd positioning. | `AnalystOpinion` |
| On-chain Analyst | `committee.analysts` | Exchange flows, whales, stablecoins, institutional wallets. | `AnalystOpinion` |
| Statistical Analyst | `committee.analysts` | Regime-aware statistical edges; consumes selected strategies' signals. | `AnalystOpinion` |
| **Risk Manager** | `committee.risk_manager` | Screens the trade; can **veto** (absolute, I5). | `RiskAssessment` |
| **AI Challenger** (devil's advocate) | `committee.challenger` | Officially contests the Chair's provisional call with counter-evidence, forcing a second debate before it is final (M6, module 17). | `ChallengeResult` |
| **Auditor** | `learning.audit` | Post-hoc: mines closed trades for what failed and why; proposes weight/strategy adjustments. | audit report |
| **Meta-Risk** | `risk.meta` | Oversees the Risk Manager itself: too conservative? over-blocking? limits stale vs regime? (M9, module 23). | `MetaRiskReport` |
| **Executor** | `execution` + `paper` | Routes an approved decision to the **paper** broker only (I1). | `TradeRecord` |

### Decision hierarchy (the Chair's rules, in order)

1. **Regime gate** — if the Regime Engine reports an untradeable regime (e.g.
   `CRISIS` with no validated families), stand down.
2. **Risk veto** — any Risk Manager veto blocks the trade → `FLAT` (I5).
3. **Evidence threshold** — trade only if composite confidence *and* agreement
   clear their thresholds.
4. Otherwise **stand down** (insufficient evidence). Standing down is a valid,
   logged outcome — not a failure.

### Debate protocol (M6, optional)

Default (M1): analysts run independently, the confidence model aggregates, the
Chair decides — simple and fully deterministic. Optional (M6, LangGraph or a
plain-Python loop): each analyst sees a summary of peers and may revise **once**
before the Chair decides. The debate must still produce the same
`CommitteeDecision` type and honour the same hierarchy (regime gate, then veto,
then threshold).

**AI Challenger (M6, module 17).** Before a provisional decision is finalised, an
official Challenger tries to break it — it argues the opposite side with
counter-evidence drawn from the same snapshot/regime. If it raises a material
objection, the Chair runs one more debate round incorporating it. This makes
decisions more robust and, crucially, records *why* the objection was or wasn't
decisive (I4). The Challenger never has a veto (that is the Risk Manager's alone,
I5); it only forces reconsideration.

---

## 4. The regime-aware decision flow (target state)

This is the flow that makes the platform "learn what works when", not "find one
winner". Read it top to bottom.

```
DataLake.snapshot(symbol, tf, at)                 # M2: point-in-time multi-channel
   │
   ├─ AnomalyDetector.flags()                     # M4: unusual conditions as context
   │
   ├─ RegimeClassifier.classify()  ──▶ RegimeState# M4: what market are we in? (explainable)
   │
   ├─ MetaLearner.select(regime, universe)        # M7: ONLY strategies validated for THIS regime
   │        └─ selected strategies emit signals   # M5: feed the Statistical Analyst / spawn analysts
   │
   └─ InvestmentCommittee.deliberate(snapshot, ctx={regime, anomalies, signals})
            │  analysts → ConfidenceModel → ConfidenceCalibrator → RiskManager
            │                                └─ M7: correct over/under-confidence from history
            ├─ Challenger.contest(provisional)  # M6: devil's advocate ▶ maybe one more round
            └─ Chair.decide()   [regime gate ▶ risk veto ▶ threshold]
                     │
                     ├─ explain_decision()         # M1: narrative + reasons + risks
                     ├─ DecisionArchive.record()    # M7: dossier (regime, strategies, evidence)
                     │        └─ later: outcome ▶ MetaLearner.update() + Calibrator.fit()
                     │                          + Auditor + Meta-Risk    # closes the loop
                     ├─ PaperExecutionEngine.execute()   # paper only (I1)
                     └─ Hermes.on_event(decision/veto/regime/anomaly)   # M8: push alert (read-only)
```

The loop is closed: outcomes recorded in the archive feed the Meta-Learner (which
strategy families to trust per regime) and the Auditor (which components to fix).
Every arrow's inputs and outputs are serialised into the decision's `run_manifest`
so the whole path is reproducible (I8).

### 4.1 The self-improvement loop (the scientific lab, M9)

Above the per-decision loop runs a slower, periodic loop that keeps the whole
system healthy and pushes it to learn — this is what turns quantos from a research
platform into a research *lab*.

```
DecisionArchive + Experiment Registry (M7)        # every decision AND every experiment recorded
        │
        ├─ Confidence Calibration (M7)   ─ is stated confidence honest? recalibrate.
        ├─ Knowledge Engine (M9)         ─ mine news/on-chain/macro into a relationship graph
        │                                  (ETF → BlackRock → positive news → rally → bull regime)
        ├─ Portfolio Intelligence (M9)   ─ cross-asset correlations/exposure (BTC/ETH/NASDAQ/gold/USD)
        ├─ Meta-Risk (M9)                ─ audit the Risk Manager: too conservative? over-blocking?
        │                                  limits stale vs the new regime?
        └─ Self-Evaluation (M9, weekly)  ─ which modules/datasets/indicators/agents are decaying?
                 │
                 └─ Hypothesis Generator (M9)
                        │   "which indicators lost predictive power?"
                        │   "which strategies are dying?" "what new variables to investigate?"
                        └─ new Experiments ▶ Experiment Registry ▶ Strategy Lab / research cycle
```

Design rules for this loop: it **proposes, never auto-executes structural
changes** — a human (or an explicit, logged policy) approves weight/limit changes;
every proposal is an `Experiment` with a hypothesis and a recorded conclusion
(reproducible, I8); and it can only ever affect the **paper** system (I1). The
Knowledge Engine and Portfolio Intelligence also feed *forward* into the
per-decision loop (as committee context and risk limits), not just backward.

---

## 5. Tech stack (decisions + rationale)

| Concern | Choice | Rationale / offline fallback |
| ------- | ------ | ---------------------------- |
| Language | Python ≥3.10 | matches vision + ecosystem |
| Core deps | numpy, pandas | keep the core dependency-light |
| Time-series store | **TimescaleDB** (hot) | SQL + hypertables; offline **DuckDB + Parquet** |
| Cache / bus | **Redis** | quotes cache, pub/sub; offline in-process |
| Market/derivs data | **ccxt** (read-only) | synthetic generator when absent |
| On-chain/macro/sentiment/news | pluggable `Connector`s | each ships a synthetic offline mode (I6) |
| Backtesting | in-house vectorised + **vectorbt** (optional) | in-house always available |
| Perf reporting | **QuantStats** (optional) | our `metrics.py` is the baseline |
| ML / anomaly | scikit-learn, **PyOD**, **Prophet** | Isolation Forest / z-score baseline |
| Regime classification | scikit-learn (HMM/GMM/rules), **hmmlearn** (opt) | rule + statistical baseline, no heavy dep |
| Optimisation / GA | **Optuna**, **DEAP**, Nevergrad | dependency-free GA baseline first |
| Agent orchestration | **LangGraph** (optional) | committee works without it |
| LLM access | **Claude** (primary), OpenRouter/Ollama pluggable | via `LLMClient` port; rule-based default |
| Dashboard | **Streamlit** (primary), Grafana for infra | reads Store + Archive |
| Experiment tracking | **MLflow** | logs backtests/GA/meta runs; local file offline |
| LLM observability | **Langfuse** (optional) | traces analyst/LLM calls |
| Infra metrics | Prometheus + Grafana | scrape ingestors + paper engine |
| Automation | **n8n**, GitHub Actions | scheduled ingestion / CI |
| Packaging | Docker + docker-compose | one command spins Timescale+Redis+dashboard |

> **Dependency policy.** The **core** stays importable with only numpy+pandas.
> Everything heavier lives behind optional extras (`[data]`, `[research]`, `[ml]`,
> `[llm]`, `[dashboard]`, `[infra]`) and lazy imports. This preserves I6.

---

## 6. Non-functional requirements

These are contractual: every milestone must keep them true, and the builder must
add tests/checks that assert them where applicable.

| Area | Requirement |
| ---- | ----------- |
| **Reproducibility (I8)** | Every backtest/decision is replayable to the same result. Seeds are explicit; data schema versions, strategy spec versions and model artifact hashes are pinned into a `run_manifest` stored with the decision. No wall-clock or unseeded randomness in research paths. |
| **Latency** | Research/offline: a single committee decision on a warm snapshot completes in < 250 ms (rule-based analysts). LLM analysts (M6) are async and bounded by a per-call timeout with graceful abstention on breach. |
| **Throughput** | Ingestion sustains all configured connectors at their cadence for the full symbol universe without falling behind (monitored via freshness/lag; see Data Infra §5). |
| **Data retention & tiering** | Raw tier retained per policy (default: keep all; configurable TTL); curated + features retained indefinitely. Partitioned by symbol/date for prune-friendly reads. |
| **Availability / 24-7** | Ingestion runs continuously; a failing connector degrades gracefully (circuit breaker) without stopping others. Scheduler + gap-repair recover missed windows on restart (watermarks). |
| **Backups & recovery** | Store artifacts (Parquet/Timescale) are backupable; the lake can be rebuilt from raw tier + connector replays. Watermarks make ingestion resumable after a crash. |
| **Security & secrets** | No secret in code or git. Keys only via env/secret manager, only for optional live-data connectors. Live execution stays disabled (I1). Read-only market access by default. |
| **Cost** | Offline research path has zero external cost. LLM and paid-data usage is opt-in, per-call metered, and logged (MLflow/Langfuse) so cost is attributable. |
| **Observability** | Every connector reports health (freshness, success rate, lag); every decision and backtest is logged and queryable; dashboards surface equity/drawdown/risk and "AI thinking" in real time. |
| **Testability** | Whole suite runs offline, deterministically, with no keys, fast (target < ~5 s for the core). Each invariant has at least one guarding test. |

---

## 7. Repository evolution

```
quant/
├── pyproject.toml            # extras: data, research, ml, llm, dashboard, infra
├── docker-compose.yml        # timescaledb + redis + dashboard
├── ARCHITECTURE.md · BUILD_PLAN.md · docs/DATA_INFRASTRUCTURE.md
├── quantos/
│   ├── data/  schema/ store/ connectors/ ingest/ quality/ catalog.py featurestore.py lake.py
│   ├── features/                  # indicators, regime features
│   ├── committee/                 # analysts, confidence, risk_manager, chair, committee, llm, debate
│   ├── anomaly/                   # detectors (M4)
│   ├── regime/                    # RegimeClassifier + RegimeState (M4)
│   ├── strategy/                  # base, generator, lab, evolution (M5)
│   ├── meta/                      # MetaLearner + RegimePerformanceTable (M7)
│   ├── memory/                    # archive, rag (M7)
│   ├── learning/                  # audit / Auditor (M7), self_eval (M9)
│   ├── scenarios/                 # library + simulator; real-time replay (M4/M9)
│   ├── knowledge/                 # KnowledgeGraph + KnowledgeEngine (M9)
│   ├── portfolio/                 # PortfolioAnalyzer, correlations (M9)
│   ├── research/                  # experiments registry, hypotheses (M7/M9)
│   ├── risk/                      # limits (M3), meta-risk (M9)
│   ├── committee/                 # + challenger (M6), calibration (M7)
│   ├── explain/  backtest/ (+ validation)  paper/  execution/ (+ costs)  # M1/M3
│   ├── sizing/                    # PositionSizer (M3)
│   ├── hermes/                    # comms agent: channels + notifier (M8, read-only)
│   └── dashboard/                 # Streamlit (M8)
└── tests/                         # mirror every package, offline & deterministic
```

---

## 8. Milestone roadmap (dependency-ordered)

```
M1  Investment Committee (analysts, confidence, risk veto, chair, explain,
    backtest→WF→MC, paper) — the differentiator, BUILT FIRST
M2  Data Infrastructure (professional: connectors, schema, store, ingest,
    feature store) — unlocks real multi-channel data for everything
M3  Risk Engine hardening + Forward test — completes the validation funnel
M4  Market State Intelligence: Anomaly detection + Market Regime Engine +
    Scenario simulator
M5  Strategy Lab: AI strategy generator + genetic evolution
M6  LLM-backed analysts + LangGraph debate
M7  Memory & Learning: Decision Archive + RAG memory + Continuous audit +
    Meta-Learning Engine (regime × strategy-family selection) +
    Confidence Calibration + Experiment Registry
M8  Presentation & Delivery: Dashboard + Hermes (comms agent) + Observability
    (MLflow / Prometheus / Grafana)
M9  Advanced Intelligence & Self-Improvement: Knowledge Engine + Portfolio
    Intelligence + Meta-Risk + Self-Evaluation + Hypothesis Generator +
    Market Simulator (real-time replay). Also M6: AI Challenger.
```

Regime-aware strategy selection comes online when M4 (regimes) and M7 (meta) are
both built; until then the committee runs regime-agnostic. The M9 self-improvement
loop (§4.1) needs a mature system (M2 data, M5 strategies, M7 archive) before it
has anything to reason over. Each milestone is a set of **work packages** in
`BUILD_PLAN.md`, each sized to build+test in one pass and preserving every
invariant in §0.

---

## 9. Cross-cutting conventions (bind on the builder)

1. **House style.** dataclasses for records, `Protocol`/ABC for ports, `as_dict()`
   for serialisation, full type hints, docstrings at real density.
2. **Offline-first.** Every module ships a deterministic synthetic path + a test
   that runs with no network and no keys.
3. **Tests are part of the WP.** No WP is done without deterministic tests
   asserting its acceptance criteria; the suite stays green and fast.
4. **No secrets in code or git.** New config via `Settings` + `.env.example`.
5. **Preserve safety.** Touching execution keeps I1 provably true (guarding test).
6. **Reproducible (I8).** Seeded everywhere; pin versions/artifacts into the
   decision `run_manifest`.
7. **Small, reviewable commits** per WP with the WP id in the message.
8. **Docs.** Update the module table (§2.2) and README when a WP lands.

### 9.1 Engineering standards (enforced from WP-0)

Quality tooling is not optional garnish — it is what keeps a 26-module system
from rotting as it grows. All of it runs offline and in CI.

- **CI (GitHub Actions):** run the full offline suite on every push; a red suite
  blocks the merge. This is the outermost guardrail on every invariant.
- **Lint + format:** `ruff` (lint + format), enforced in CI and via `pre-commit`.
- **Types:** `mypy` on `quantos/` (public interfaces fully typed); CI-enforced.
- **Property-based tests (`hypothesis`)** for the hard invariants — I2 (no
  look-ahead) and I8 (reproducibility) are asserted over generated inputs, not a
  single fixture. Example: for random valid OHLCV, a signal computed at bar *t*
  must not change when bars > *t* are perturbed.
- **Golden / regression tests:** a pinned decision and a pinned backtest must
  replay bit-for-bit (I8); a diff fails CI.
- **Benchmark harness:** every backtest reports its metrics **alongside
  buy-and-hold and a random baseline** — a strategy that can't beat both is not
  evidence of an edge (guards against self-deception, complements I9).

This is the architecture. Build it in the order and shape defined by
`BUILD_PLAN.md`.
