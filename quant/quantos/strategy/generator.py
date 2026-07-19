"""AI strategy generator (module 5, WP-5.2): the platform invents strategies.

Two backends behind one interface:

- :class:`RandomStrategyGenerator` — the **default, offline** backend: a
  deterministic random/grammar search over the building-block registry of
  :mod:`quantos.strategy.base`. A pure function of ``(n, seed, diversity)``
  (invariant I8) needing no network and no keys (I6).
- :class:`LLMStrategyGenerator` — an **optional** backend behind the
  :class:`LLMClient` port (implemented for real in M6): the model proposes
  original specs as JSON with a stated ``rationale`` and ``target_regimes``.
  :class:`MockLLMClient` is the deterministic offline stand-in; no test ever
  requires a real LLM.

Both backends enforce the same gates before a spec leaves the generator:

- **validity** — every spec is compiled and executed on a synthetic frame
  (runnable, signals within [-1, 1]);
- **uniqueness** — no two specs share a content hash *or* an indicator set;
- **diversity** — the batch's mean pairwise Jaccard distance between
  indicator sets must clear the ``diversity`` threshold.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantos.data.collector import synthetic_ohlcv
from quantos.llm.client import LLMClient, MockLLMClient
from quantos.strategy.base import (
    IndicatorStrategy,
    Rule,
    StrategyRegistry,
    StrategySpec,
    registry,
)

__all__ = [
    "DEFAULT_FAMILIES",
    "FamilyTemplate",
    "GenerationError",
    "LLMClient",
    "LLMStrategyGenerator",
    "MockLLMClient",
    "RandomStrategyGenerator",
    "diversity_score",
    "generate",
    "validate_spec",
]


class GenerationError(RuntimeError):
    """Raised when a backend cannot produce the requested batch honestly."""


# ---------------------------------------------------------------------------
# The grammar: strategy families over the block registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FamilyTemplate:
    """The grammar of one strategy family.

    Attributes:
        name: family name — the unit the Meta-Learner (M7) validates per regime.
        indicator_pool: blocks this family draws from.
        comparator_pool: comparators this family draws from.
        target_regimes: regimes specs of this family declare themselves for.
        rationale: the family's economic story (auditability, I4).
    """

    name: str
    indicator_pool: tuple[str, ...]
    comparator_pool: tuple[str, ...]
    target_regimes: tuple[str, ...]
    rationale: str


#: The default family grammar over the default block registry.
DEFAULT_FAMILIES: tuple[FamilyTemplate, ...] = (
    FamilyTemplate(
        "trend",
        ("ema_ratio", "sma_ratio", "macd_hist", "momentum", "channel_pos", "atr_ratio"),
        ("gt", "lt", "cross_above", "cross_below"),
        ("TREND_UP", "TREND_DOWN"),
        "persistent moves continue: side with the prevailing trend",
    ),
    FamilyTemplate(
        "mean_reversion",
        ("zscore", "rsi", "bollinger_b", "sma_ratio", "vol_zscore"),
        ("gt", "lt"),
        ("RANGE",),
        "stretched prices snap back toward their rolling anchor",
    ),
    FamilyTemplate(
        "momentum",
        ("momentum", "rsi", "macd_hist", "ema_ratio", "sma_ratio"),
        ("gt", "lt", "cross_above"),
        ("TREND_UP", "TREND_DOWN"),
        "recent winners keep winning over short horizons",
    ),
    FamilyTemplate(
        "breakout",
        ("channel_pos", "atr_ratio", "vol_zscore", "momentum", "bollinger_b"),
        ("gt", "cross_above", "abs_gt"),
        ("HIGH_VOL", "TREND_UP"),
        "range escapes on expanding volatility start new legs",
    ),
    FamilyTemplate(
        "volatility",
        ("vol_zscore", "atr_ratio", "bollinger_b", "zscore", "momentum"),
        ("gt", "lt", "abs_gt"),
        ("HIGH_VOL", "LOW_VOL"),
        "volatility regimes cluster: position for the prevailing vol state",
    ),
)


# ---------------------------------------------------------------------------
# Gates shared by every backend
# ---------------------------------------------------------------------------


def diversity_score(specs: Sequence[StrategySpec]) -> float:
    """Mean pairwise Jaccard *distance* between the specs' indicator sets.

    1.0 means fully disjoint indicator sets, 0.0 means identical ones. A
    batch of fewer than two specs is trivially diverse (1.0).
    """
    if len(specs) < 2:
        return 1.0
    sets = [spec.indicator_set() for spec in specs]
    total = 0.0
    pairs = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = len(sets[i] | sets[j])
            inter = len(sets[i] & sets[j])
            total += 1.0 - (inter / union if union else 1.0)
            pairs += 1
    return total / pairs


#: Bars in the validation frame every generated spec must run on.
_VALIDATION_BARS = 96


def validate_spec(
    spec: StrategySpec,
    blocks: StrategyRegistry | None = None,
    ohlcv: pd.DataFrame | None = None,
) -> bool:
    """True when a spec compiles and produces bounded signals (runnable gate).

    Args:
        spec: the candidate spec.
        blocks: registry to compile against (module default when omitted).
        ohlcv: frame to exercise the strategy on; a fixed deterministic
            synthetic frame when omitted (I6/I8).
    """
    frame = (
        ohlcv
        if ohlcv is not None
        else synthetic_ohlcv("GEN/VALID", "1h", bars=_VALIDATION_BARS, seed=11)
    )
    try:
        signals = IndicatorStrategy(spec, blocks=blocks).signals(frame)
    except Exception:
        return False
    return (
        isinstance(signals, pd.Series)
        and len(signals) == len(frame)
        and bool(signals.between(-1.0, 1.0).all())
        and not bool(signals.isna().any())
    )


def _screen_batch(
    specs: Sequence[StrategySpec], n: int, diversity: float, backend: str
) -> list[StrategySpec]:
    """Apply the uniqueness + diversity gates to a candidate batch."""
    if len(specs) < n:
        raise GenerationError(
            f"{backend} produced only {len(specs)} valid unique specs of {n} requested"
        )
    batch = list(specs[:n])
    score = diversity_score(batch)
    if score < diversity:
        raise GenerationError(
            f"{backend} batch diversity {score:.3f} below the required {diversity:.3f}"
        )
    return batch


# ---------------------------------------------------------------------------
# Default backend: deterministic random/grammar search (offline, I6)
# ---------------------------------------------------------------------------


class RandomStrategyGenerator:
    """Deterministic grammar search over the building-block registry.

    ``generate(n, seed, diversity)`` is a pure function of its arguments
    (I8): specs are sampled family-by-family from :data:`DEFAULT_FAMILIES`
    (or a custom grammar), deduplicated on indicator set *and* content hash,
    validated runnable, and gated on the batch diversity metric.
    """

    def __init__(
        self,
        blocks: StrategyRegistry | None = None,
        families: Sequence[FamilyTemplate] = DEFAULT_FAMILIES,
        max_indicators: int = 4,
        version: str = "1",
    ) -> None:
        """
        Args:
            blocks: block registry (the module default when omitted).
            families: the family grammar to sample from.
            max_indicators: largest indicator set a spec may use.
            version: version string stamped on every generated spec (I8).
        """
        if not families:
            raise ValueError("need at least one family template")
        self._registry = blocks if blocks is not None else registry
        self.families = tuple(families)
        self.max_indicators = max_indicators
        self.version = version

    # -- sampling ----------------------------------------------------------

    def _sample_spec(self, rng: np.random.Generator, index: int) -> StrategySpec:
        """Draw one candidate spec from the grammar."""
        family = self.families[int(rng.integers(len(self.families)))]
        size_cap = min(self.max_indicators, len(family.indicator_pool))
        size = int(rng.integers(1, size_cap + 1))
        chosen = rng.choice(len(family.indicator_pool), size=size, replace=False)
        names = tuple(sorted(family.indicator_pool[int(i)] for i in chosen))

        params: dict[str, float] = {}
        rules: list[Rule] = []
        for name in names:
            block = self._registry.indicator(name)
            for pspec in block.params:
                params[f"{name}.{pspec.name}"] = pspec.sample(rng)
            comparator = family.comparator_pool[int(rng.integers(len(family.comparator_pool)))]
            threshold = block.threshold.sample(rng)
            action = 1 if rng.random() < 0.5 else -1
            rules.append(Rule(name, comparator, threshold, action))
            if rng.random() < 0.5:  # sometimes add the mirrored counter-rule
                mirror = {"gt": "lt", "lt": "gt", "cross_above": "cross_below"}.get(comparator)
                if mirror in family.comparator_pool:
                    assert mirror is not None
                    rules.append(Rule(name, mirror, block.threshold.sample(rng), -action))

        return StrategySpec(
            name=f"{family.name}-{'-'.join(names)}-{index:03d}",
            version=self.version,
            family=family.name,
            indicators=names,
            rules=tuple(rules),
            params=params,
            target_regimes=family.target_regimes,
            rationale=(
                f"grammar search over {', '.join(names)}: {family.rationale}"
            ),
        )

    def generate(self, n: int, seed: int = 0, diversity: float = 0.25) -> list[StrategySpec]:
        """Produce ``n`` distinct, valid, diverse specs deterministically.

        Args:
            n: number of specs required.
            seed: RNG seed — same seed, same batch (I8).
            diversity: minimum batch :func:`diversity_score`.

        Returns:
            Exactly ``n`` specs, each runnable, with pairwise-distinct
            indicator sets and content hashes.

        Raises:
            GenerationError: when the grammar cannot honestly satisfy the
                request (too few distinct indicator sets, or diversity below
                the gate).
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        rng = np.random.default_rng(seed)
        specs: list[StrategySpec] = []
        seen_sets: set[frozenset[str]] = set()
        seen_hashes: set[str] = set()
        attempts = 0
        max_attempts = max(500, 60 * n)
        while len(specs) < n and attempts < max_attempts:
            attempts += 1
            candidate = self._sample_spec(rng, index=len(specs))
            iset = candidate.indicator_set()
            chash = candidate.spec_hash()
            if iset in seen_sets or chash in seen_hashes:
                continue
            if not validate_spec(candidate, blocks=self._registry):
                continue
            specs.append(candidate)
            seen_sets.add(iset)
            seen_hashes.add(chash)
        return _screen_batch(specs, n, diversity, backend="RandomStrategyGenerator")


# ---------------------------------------------------------------------------
# Optional backend: LLM-proposed strategies behind the LLMClient port
# ---------------------------------------------------------------------------


# The canonical LLM port lives in ``quantos.llm.client`` (M6); ``LLMClient``
# and ``MockLLMClient`` are re-exported here unchanged for back-compat — one
# port, one mock, no forks (I7).


class LLMStrategyGenerator:
    """LLM-backed generation behind the :class:`LLMClient` port (optional).

    The client is asked for ``n`` spec proposals as JSON; every proposal is
    parsed, validated runnable, deduplicated (hash + indicator set) and the
    batch is gated on diversity — the same discipline as the offline
    backend. Malformed proposals are skipped, never repaired silently into
    the batch.
    """

    def __init__(self, client: LLMClient, blocks: StrategyRegistry | None = None) -> None:
        self.client = client
        self._registry = blocks if blocks is not None else registry

    def _prompt(self, n: int) -> str:
        """The generation prompt: the grammar the model must stay inside."""
        return (
            f"Propose n={n} distinct quantitative strategy specs as a JSON array. "
            f"Allowed indicator blocks: {', '.join(self._registry.indicator_names())}. "
            f"Allowed comparators: {', '.join(self._registry.comparator_names())}. "
            "Each spec: name, version, family, indicators, rules "
            "(indicator/comparator/threshold/action), params, target_regimes, "
            "and a one-line rationale. Research only — no live trading (I1)."
        )

    def generate(self, n: int, seed: int = 0, diversity: float = 0.25) -> list[StrategySpec]:
        """Produce ``n`` validated specs from LLM proposals.

        Args:
            n: number of specs required.
            seed: forwarded to deterministic clients via the prompt contract
                (the mock is seeded at construction; kept for interface
                parity with the offline backend, I8).
            diversity: minimum batch :func:`diversity_score`.

        Raises:
            GenerationError: when the client's proposals cannot fill a valid,
                unique, diverse batch of ``n``.
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        raw = self.client.complete(self._prompt(n), schema={"type": "array"})
        try:
            proposals = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GenerationError(f"LLM returned malformed JSON: {exc}") from exc
        if not isinstance(proposals, list):
            raise GenerationError("LLM response must be a JSON array of specs")

        specs: list[StrategySpec] = []
        seen_sets: set[frozenset[str]] = set()
        seen_hashes: set[str] = set()
        for item in proposals:
            try:
                spec = StrategySpec.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue  # malformed proposal: skipped, never fabricated (I3 spirit)
            iset = spec.indicator_set()
            chash = spec.spec_hash()
            if iset in seen_sets or chash in seen_hashes:
                continue
            if not validate_spec(spec, blocks=self._registry):
                continue
            specs.append(spec)
            seen_sets.add(iset)
            seen_hashes.add(chash)
        return _screen_batch(specs, n, diversity, backend="LLMStrategyGenerator")


# ---------------------------------------------------------------------------
# The front door
# ---------------------------------------------------------------------------


def generate(
    n: int,
    seed: int = 0,
    diversity: float = 0.25,
    backend: RandomStrategyGenerator | LLMStrategyGenerator | None = None,
) -> list[StrategySpec]:
    """Generate ``n`` distinct, valid, diverse strategy specs.

    The default backend is the offline deterministic grammar search — no
    network, no keys (I6), same ``(n, seed, diversity)`` in, same specs out
    (I8). Pass an :class:`LLMStrategyGenerator` to use a model instead.
    """
    engine = backend if backend is not None else RandomStrategyGenerator()
    return engine.generate(n, seed=seed, diversity=diversity)
