# Data Infrastructure — professional design (Milestone 2)

> Architect spec (Opus) for the builder (Fable 5). The Data Lake is the
> platform's **primary asset**: a modular, schema-versioned, validated, monitored
> ingestion system designed to run **24/7 for years**, add new sources without
> touching the core, and serve quant research, backtesting, ML and real-time
> analysis. Honours all invariants in [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §0
> — especially **I2 (no look-ahead)** and **I6 (offline, no secrets)**.

---

## 1. Principles

1. **Connectors are plugins.** Each data source is an independent `Connector`
   that self-registers. Adding a source = add one module; the core never changes
   (Open/Closed). No `if source == "x"` branching anywhere in the core.
2. **Schema-first & versioned.** Every dataset has an explicit, versioned
   `Schema`. Data is validated against it on write. Schema evolution goes through
   registered migrations — never silent column drift.
3. **Point-in-time correct.** Every record carries an `event_time` (when it was
   true in the market) distinct from `ingested_at` (when we stored it). All reads
   for research are **as-of** joins → no look-ahead (I2).
4. **Idempotent & resumable.** Ingestion upserts on primary keys and tracks a
   **watermark** per (connector, symbol). Re-running never duplicates; a crash
   resumes from the last watermark.
5. **Resilient.** Fetches run under a `RetryPolicy` (exponential backoff + jitter)
   and a `CircuitBreaker`. A failing source degrades gracefully; it never takes
   down ingestion of the others.
6. **Observable.** Every connector reports health: freshness/lag, success rate,
   rows/interval, last error. Surfaced as a dict and (optional) Prometheus.
7. **Tiered storage.** `raw` (as fetched) → `curated` (validated, typed, deduped)
   → `features` (ML/research-ready). Each tier is queryable.
8. **Offline-first.** Every connector has a deterministic `synthetic` mode; the
   whole system runs and tests with **no network and no keys** (I6). Real
   backends (ccxt, HTTP APIs, Timescale, Redis) are optional, lazy-imported, and
   never hardcode a provider key.

---

## 2. Component map

```
quantos/data/
├── schema/
│   ├── base.py          FieldSpec, Schema, SchemaVersion
│   ├── registry.py      SchemaRegistry (versions + latest), Migration
│   └── validation.py    DataValidator -> ValidationReport
├── connectors/
│   ├── base.py          Connector (ABC), ConnectorMetadata, FetchRequest, FetchResult, HealthStatus
│   ├── registry.py      ConnectorRegistry + @register decorator (self-registration)
│   ├── market.py        OHLCV / trades / order book (ccxt + synthetic)
│   ├── derivatives.py   funding, open_interest, long_short_ratio, basis, liquidations
│   ├── onchain.py       net_exchange_flow, whale_accumulation, stablecoin_supply
│   ├── macro.py         dxy, rates, cpi/ppi/nfp, fomc event flags
│   ├── sentiment.py     social score + per-platform breakdown
│   └── news.py          headlines + tag + sentiment
├── store/
│   ├── base.py          Store (Protocol): write/read/upsert/tiers
│   ├── duckdb_store.py   DuckDB+Parquet (offline default; pure-pandas fallback)
│   └── timescale_store.py Timescale hypertables (optional, extra [infra])
├── ingest/
│   ├── retry.py         RetryPolicy, backoff, CircuitBreaker
│   ├── watermark.py     Watermark store (per connector+symbol)
│   ├── runner.py        IngestionRunner: fetch→validate→upsert→watermark→metrics
│   ├── gaps.py          gap detection + backfill/repair
│   └── scheduler.py     Scheduler for 24/7 (interval jobs); offline run_due()
├── quality/
│   └── monitor.py       HealthMonitor: freshness, success rate, rows, lag
├── catalog.py           DataCatalog: datasets, schema+version, lineage, freshness
├── featurestore.py      FeatureStore.as_of(...) — point-in-time-correct features
└── lake.py              DataLake facade (ingest / snapshot / query)
```

---

## 3. Key contracts (build to these signatures)

### 3.1 Schema
```python
@dataclass(frozen=True)
class FieldSpec:
    name: str; dtype: str; nullable: bool = False
    description: str = ""; unit: str | None = None
    min: float | None = None; max: float | None = None

@dataclass(frozen=True)
class Schema:
    name: str
    version: int
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...]        # e.g. ("symbol", "event_time")
    time_column: str = "event_time"     # point-in-time key (I2)

class SchemaRegistry:
    def register(self, schema: Schema) -> None: ...
    def latest(self, name: str) -> Schema: ...
    def get(self, name: str, version: int) -> Schema: ...
    def add_migration(self, m: "Migration") -> None: ...
    def migrate(self, df, name: str, from_v: int, to_v: int) -> "DataFrame": ...
```

### 3.2 Validation
```python
@dataclass
class ValidationReport:
    ok: bool; errors: list[str]; warnings: list[str]; rows: int; dropped: int

class DataValidator:
    def validate(self, df, schema: Schema, *, coerce: bool = True) -> tuple["DataFrame", ValidationReport]:
        # checks: required columns, dtypes (coerce if asked), non-null on
        # non-nullable, primary-key uniqueness, monotonic non-decreasing
        # time_column, min/max range. Returns cleaned frame + report.
```

### 3.3 Connector
```python
@dataclass(frozen=True)
class ConnectorMetadata:
    name: str; category: str; schema_name: str
    cadence_seconds: int                 # expected update interval (for freshness)
    offline_capable: bool = True

@dataclass(frozen=True)
class FetchRequest:
    symbol: str; start=None; end=None; timeframe: str = "1h"; limit: int = 1000
    mode: str = "auto"                   # auto | live | synthetic

@dataclass
class FetchResult:
    rows: "DataFrame"; schema_version: int; source_mode: str

@dataclass
class HealthStatus:
    healthy: bool; last_success=None; last_error: str | None; latency_ms: float | None

class Connector(ABC):
    metadata: ConnectorMetadata
    @abstractmethod
    def fetch(self, req: FetchRequest) -> FetchResult: ...
    @abstractmethod
    def synthetic(self, req: FetchRequest) -> FetchResult: ...   # deterministic, offline
    def healthcheck(self) -> HealthStatus: ...                   # default: cheap probe
```

### 3.4 Registry (self-registration, no core edits)
```python
class ConnectorRegistry:
    def register(self, connector: Connector) -> None: ...
    def get(self, name: str) -> Connector: ...
    def by_category(self, category: str) -> list[Connector]: ...
    def all(self) -> list[Connector]: ...

registry = ConnectorRegistry()           # module-level singleton
def register(cls):                        # class decorator -> instantiates & registers
    registry.register(cls()); return cls
```
Adding a source = write a `Connector` subclass decorated with `@register`. The
`DataLake` discovers it through the registry. **No core file is edited.**

### 3.5 Store (tiered)
```python
class Store(Protocol):
    def write(self, tier: str, table: str, df, schema: Schema) -> int: ...
    def upsert(self, tier: str, table: str, df, keys: list[str]) -> int: ...
    def read(self, tier: str, table: str, symbol=None, start=None, end=None) -> "DataFrame": ...
    def tables(self, tier: str) -> list[str]: ...
# tiers: "raw" | "curated" | "features"
```

### 3.6 Ingestion runner (resilient, idempotent)
```python
@dataclass
class RetryPolicy:
    max_attempts: int = 5; base_delay: float = 1.0; max_delay: float = 60.0; jitter: bool = True

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 300.0): ...
    def allow(self) -> bool: ...
    def record(self, ok: bool) -> None: ...

class IngestionRunner:
    def __init__(self, store, validator, watermarks, monitor, retry=RetryPolicy()): ...
    def run(self, connector: Connector, req: FetchRequest) -> ValidationReport:
        # 1) circuit-breaker gate  2) fetch under RetryPolicy (backoff+jitter)
        # 3) validate against latest schema  4) write raw + upsert curated
        # 5) advance watermark  6) record health metrics. Idempotent.
```

### 3.7 Feature store (point-in-time correct)
```python
class FeatureStore:
    def as_of(self, symbol: str, at, features: list[str]) -> dict:
        # as-of (backward) join across curated tables using event_time <= at.
        # NEVER returns a value whose event_time > at (I2).
    def frame(self, symbol, start, end, features, freq) -> "DataFrame": ...
```

### 3.8 DataLake facade (what the committee uses)
```python
class DataLake:
    def __init__(self, store=None, registry=registry, ...): ...
    def ingest(self, symbol, timeframe, start=None, end=None, categories=None) -> dict[str, ValidationReport]:
        # run every registered connector (or a category subset) through the runner
    def repair_gaps(self, symbol, timeframe) -> dict: ...
    def snapshot(self, symbol, timeframe, limit=500, at=None) -> MarketSnapshot:
        # assemble a point-in-time MarketSnapshot from curated tiers so ALL
        # analysts participate (0 abstentions). `at` enables historical snapshots.
    def catalog(self) -> DataCatalog: ...
    def health(self) -> dict: ...
```

---

## 4. Data model conventions

- Every table has `event_time` (UTC, tz-aware) and `ingested_at`. Primary keys
  always include `symbol` + `event_time` (or a natural id for news).
- Timestamps are tz-aware UTC, non-decreasing per symbol. Validation enforces it.
- Numeric ranges validated (e.g. `funding_rate` within sane bounds, `score` in
  [-1, 1]). Out-of-range → warning + optional clamp, logged in lineage.
- Storage partitioned by `symbol` and date; curated tier deduped on primary key.

---

## 5. 24/7 operation

- `Scheduler` holds jobs `(connector, symbol, cadence)`; a tick loop dispatches
  due jobs to the `IngestionRunner`. Production may back this with APScheduler or
  cron (optional); the offline/default path is `scheduler.run_due(now)` so it is
  fully testable without a running loop.
- `gaps.py` detects missing expected timestamps (from cadence) and backfills.
- `HealthMonitor` marks a connector **stale** when `now - last_event_time >
  k × cadence`, feeding the dashboard (M8) and Prometheus (optional).

---

## 6. Optional infra (all lazy, offline fallbacks)

| Capability | Real backend (extra) | Offline default |
| ---------- | -------------------- | --------------- |
| Time-series store | TimescaleDB `[infra]` | DuckDB + Parquet |
| Cache / bus | Redis `[infra]` | in-process dict/queue |
| Market data | ccxt `[data]` | synthetic generator |
| Scheduling | APScheduler `[infra]` | `run_due()` manual tick |
| Metrics | Prometheus `[infra]` | in-memory counters dict |

The core (`schema`, `connectors.base`, `store.duckdb_store`, `ingest.*`,
`quality`, `catalog`, `featurestore`, `lake`) imports with only numpy+pandas
(+duckdb if present, else pandas/parquet).

---

## 7. Acceptance for the milestone (professional bar)

1. A **new connector** can be added by writing one `@register`ed module — proven
   by a test that registers a dummy connector and sees it flow end-to-end with
   **zero core edits**.
2. **Schema versioning** works: two versions + a migration; validation rejects a
   frame that violates the schema.
3. **Idempotent ingestion**: running `ingest` twice yields identical curated row
   counts (watermark + upsert).
4. **Resilience**: a connector that raises N times is retried per policy and the
   circuit breaker opens; other connectors still ingest.
5. **Point-in-time**: `FeatureStore.as_of(t)` never returns data with
   `event_time > t` (explicit no-look-ahead test).
6. **Committee integration**: after `ingest`, `DataLake.snapshot(...)` yields a
   `MarketSnapshot` where `default_committee().deliberate(snapshot)` has **0
   abstentions**.
7. **Observability**: `DataLake.health()` reports freshness/success per connector.
8. Whole suite green, offline, no keys, fast.

---

## 8. Dataset catalog (the full lake)

Every dataset below is one `Connector` + one versioned `Schema`. All share
`symbol`, `event_time` (tz-aware UTC, point-in-time key, I2) and `ingested_at`;
only the domain fields are listed. Connectors ship a deterministic `synthetic`
mode (I6); real backends are optional and lazy. Not everything is built in M2 —
M2 delivers the framework + the starred (⭐) connectors; the rest are added later,
each with **zero core edits** (the whole point of the plug-in design).

### Market (`category="market"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| OHLCV (multi-timeframe) ⭐ | `market` | `timeframe, open, high, low, close, volume` |
| Tick / trades | `trades` | `price, size, side, trade_id` |
| VWAP | `vwap` | `vwap, window` |
| Spread | `spread` | `bid, ask, spread_abs, spread_bps` |
| Order book (L2 snapshots) | `orderbook` | `bids[[price,size]], asks[[price,size]], depth` |

### Derivatives (`category="derivatives"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| Open Interest | `open_interest` | `open_interest, oi_change` |
| Funding Rate | `funding` | `funding_rate, next_funding_time` |
| Liquidations | `liquidations` | `side, qty, price, notional` |
| Long/Short Ratio | `long_short` | `long_short_ratio, top_trader_ratio` |
| Basis | `basis` | `spot, perp, basis_abs, basis_annualised` |

### On-chain (`category="onchain"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| Exchange flows | `exchange_flows` | `inflow, outflow, net_exchange_flow` |
| Whale activity | `whales` | `whale_accumulation, large_tx_count` |
| Stablecoins | `stablecoins` | `stablecoin_supply, supply_change, exchange_reserve` |
| Institutional wallets | `institutions` | `inst_netflow, wallet_count, holdings` |

### Macro (`category="macro"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| CPI / PPI | `inflation` | `cpi, ppi, surprise` |
| FOMC / rates | `rates` | `policy_rate, rate_bias, fomc_flag` |
| NFP / labour | `labour` | `nfp, unemployment, surprise` |
| DXY | `dxy` | `dxy, dxy_trend` |
| Bonds / yields | `bonds` | `yield_2y, yield_10y, curve_slope` |
| Event calendar | `macro_events` | `event, importance, event_flag` (drives Risk veto & regime) |

### Sentiment (`category="sentiment"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| Reddit | `reddit` | `score, volume, subreddit` |
| X / Twitter | `x` | `score, volume, influencer_weighted` |
| Telegram | `telegram` | `score, volume, channel` |
| YouTube | `youtube` | `score, volume` |
| Google Trends | `google_trends` | `interest, interest_change` |
| Aggregate | `sentiment` | `score` (-1..1, blended; the one the SentimentAnalyst reads) |

### News (`category="news"`)
| Dataset | Connector | Key fields |
| ------- | --------- | ---------- |
| Tagged headlines | `news` | `source, headline, tag, sentiment, entities[]` |

News is **AI-tagged**: an LLM (M6) classifies topic, sentiment and entities. In
M2 the tagger is a deterministic keyword stub so the connector is offline-testable;
the LLM tagger swaps in behind the same schema with no downstream change.

### Derived / features (`tier="features"`)
Built by the FeatureStore and consumers, not connectors: regime features (ADX,
realised vol, Hurst — M4), strategy signals (M5), and any ML features. Always
read point-in-time (as-of) to preserve I2.
