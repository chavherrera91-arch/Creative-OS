"""Strategy contracts + building-block registry (module 5, M5 scope).

The canonical ``Strategy`` port of the whole platform (ARCHITECTURE §2.4):
anything with a ``spec`` and a causal ``signals(ohlcv) -> Series`` of target
positions in [-1, 1]. The M4 scenario simulator's ``SignalStrategy`` shape is
the structural subset of this port and is defined here (one canonical port,
not two — ``quantos.scenarios.simulator`` re-exports it).

A :class:`StrategySpec` is a *description*, not code: which indicator blocks
to compute (with which parameters) and which threshold rules vote long or
short. :class:`IndicatorStrategy` compiles a spec into signals using only the
registered building blocks — every block is built on the strictly causal
indicators of :mod:`quantos.features.indicators`, so a compiled strategy can
never look ahead (invariant I2). Specs are versioned, canonically hashable
and round-trip through ``as_dict``/``from_dict`` so any run that records a
spec hash can be replayed bit-for-bit (I8).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from quantos.features import indicators as ta
from quantos.regime.base import REGIME_LABELS

__all__ = [
    "Comparator",
    "IndicatorBlock",
    "IndicatorStrategy",
    "ParamSpec",
    "Rule",
    "SignalStrategy",
    "Strategy",
    "StrategyRegistry",
    "StrategySpec",
    "compile_spec",
    "registry",
]

IndicatorFn = Callable[[pd.DataFrame], pd.Series]
ComparatorFn = Callable[[pd.Series, float], pd.Series]


# ---------------------------------------------------------------------------
# Ports (I7) — the one canonical strategy shape
# ---------------------------------------------------------------------------


@runtime_checkable
class SignalStrategy(Protocol):
    """Anything that turns OHLCV into target positions in [-1, 1] (I7).

    This is the structural subset of :class:`Strategy` that the backtest,
    the scenario simulator and the lab consume. Signals must be causal (I2).
    """

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Target position per bar, using only bars ≤ t (I2)."""
        ...


@runtime_checkable
class Strategy(Protocol):
    """The full strategy port: a runnable signal generator plus its spec.

    ``spec`` pins name/version/params for reproducibility (I8) and carries
    ``family``/``target_regimes`` so the Meta-Learner (M7) can map families
    to regimes.
    """

    spec: StrategySpec

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Target position per bar in [-1, 1], using only bars ≤ t (I2)."""
        ...


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """A tunable parameter: name, default and legal range.

    The generator (WP-5.2) samples inside ``[low, high]`` and the GA
    (WP-5.4) mutates inside it, so every derived spec stays valid.
    """

    name: str
    default: float
    low: float
    high: float
    integer: bool = False

    def __post_init__(self) -> None:
        if not self.low <= self.default <= self.high:
            raise ValueError(
                f"{self.name}: default {self.default} outside [{self.low}, {self.high}]"
            )

    def clip(self, value: float) -> float:
        """Clamp a raw value into the legal range (rounding integer params)."""
        clipped = float(min(max(value, self.low), self.high))
        return float(round(clipped)) if self.integer else clipped

    def sample(self, rng: np.random.Generator) -> float:
        """Draw a uniform value from the legal range (deterministic given rng)."""
        if self.integer:
            return float(rng.integers(int(self.low), int(self.high) + 1))
        return float(rng.uniform(self.low, self.high))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "name": self.name,
            "default": self.default,
            "low": self.low,
            "high": self.high,
            "integer": self.integer,
        }


@dataclass(frozen=True)
class IndicatorBlock:
    """A registered indicator building block.

    Attributes:
        name: registry key, referenced by ``StrategySpec.indicators``.
        fn: ``(ohlcv, **params) -> Series`` — must be strictly causal (I2).
        params: the block's tunable parameters.
        threshold: the sensible range for rule thresholds against this
            block's output scale (used by the generator and the GA).
        description: one-line human description (auditability, I4).
    """

    name: str
    fn: Callable[..., pd.Series]
    params: tuple[ParamSpec, ...] = ()
    threshold: ParamSpec = field(
        default_factory=lambda: ParamSpec("threshold", 0.0, -1.0, 1.0)
    )
    description: str = ""

    def compute(self, ohlcv: pd.DataFrame, params: Mapping[str, float]) -> pd.Series:
        """Evaluate the block with ``params`` (falling back to defaults)."""
        kwargs: dict[str, float | int] = {}
        for spec in self.params:
            raw = float(params.get(f"{self.name}.{spec.name}", spec.default))
            value = spec.clip(raw)
            kwargs[spec.name] = int(value) if spec.integer else value
        return self.fn(ohlcv, **kwargs)


@dataclass(frozen=True)
class Comparator:
    """A registered rule comparator: ``(series, threshold) -> bool Series``."""

    name: str
    fn: ComparatorFn
    description: str = ""


class StrategyRegistry:
    """The registry of strategy building blocks (indicators + comparators).

    The generator's grammar and the GA's mutation space are exactly what is
    registered here — new blocks plug in without touching the core (I7).
    """

    def __init__(self) -> None:
        self._indicators: dict[str, IndicatorBlock] = {}
        self._comparators: dict[str, Comparator] = {}

    # -- registration ------------------------------------------------------

    def register_indicator(self, block: IndicatorBlock) -> IndicatorBlock:
        """Register an indicator block (last registration wins)."""
        self._indicators[block.name] = block
        return block

    def register_comparator(self, comparator: Comparator) -> Comparator:
        """Register a comparator (last registration wins)."""
        self._comparators[comparator.name] = comparator
        return comparator

    # -- lookup ------------------------------------------------------------

    def indicator(self, name: str) -> IndicatorBlock:
        """Fetch an indicator block by name.

        Raises:
            KeyError: for an unregistered name.
        """
        if name not in self._indicators:
            raise KeyError(f"unknown indicator block {name!r}; known: {self.indicator_names()}")
        return self._indicators[name]

    def comparator(self, name: str) -> Comparator:
        """Fetch a comparator by name.

        Raises:
            KeyError: for an unregistered name.
        """
        if name not in self._comparators:
            raise KeyError(f"unknown comparator {name!r}; known: {self.comparator_names()}")
        return self._comparators[name]

    def indicator_names(self) -> list[str]:
        """Registered indicator names, sorted (deterministic grammar, I8)."""
        return sorted(self._indicators)

    def comparator_names(self) -> list[str]:
        """Registered comparator names, sorted (deterministic grammar, I8)."""
        return sorted(self._comparators)


#: The default module-level registry every M5 component shares.
registry = StrategyRegistry()


# ---------------------------------------------------------------------------
# Spec: rules + the versioned, hashable strategy description
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One voting rule: when ``comparator(indicator, threshold)`` holds, vote.

    Attributes:
        indicator: name of a block listed in the spec's ``indicators``.
        comparator: registered comparator name.
        threshold: the comparison level, on the indicator's output scale.
        action: +1 votes long, -1 votes short when the condition holds.
        weight: relative weight of this rule's vote (> 0).
    """

    indicator: str
    comparator: str
    threshold: float
    action: int
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.action not in (-1, 1):
            raise ValueError(f"rule action must be +1 or -1, got {self.action}")
        if not self.weight > 0.0:
            raise ValueError(f"rule weight must be > 0, got {self.weight}")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "indicator": self.indicator,
            "comparator": self.comparator,
            "threshold": self.threshold,
            "action": self.action,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        """Rebuild a rule from its ``as_dict`` form."""
        return cls(
            indicator=str(data["indicator"]),
            comparator=str(data["comparator"]),
            threshold=float(data["threshold"]),
            action=int(data["action"]),
            weight=float(data.get("weight", 1.0)),
        )


@dataclass(frozen=True, eq=False)
class StrategySpec:
    """A versioned, hashable strategy description (ARCHITECTURE §2.4).

    Attributes:
        name: human-readable strategy name.
        version: spec version string, pinned into run manifests (I8).
        family: strategy family (trend, mean_reversion, ...) — the unit the
            Meta-Learner (M7) validates per regime.
        indicators: the indicator blocks the strategy computes (unique names).
        rules: the voting rules combined into the target position.
        params: flat ``"indicator.param" -> value`` overrides for the blocks.
        target_regimes: regimes this strategy declares itself for (subset of
            :data:`quantos.regime.base.REGIME_LABELS`).
        rationale: why this strategy should work (auditability, I4).
    """

    name: str
    version: str = "1"
    family: str = "generic"
    indicators: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()
    params: dict[str, float] = field(default_factory=dict)
    target_regimes: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "indicators", tuple(self.indicators))
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "target_regimes", tuple(self.target_regimes))
        object.__setattr__(self, "params", dict(self.params))
        if not self.name:
            raise ValueError("StrategySpec.name must be non-empty")
        if not self.version:
            raise ValueError("StrategySpec.version must be non-empty (I8)")
        if not self.indicators:
            raise ValueError("StrategySpec needs at least one indicator block")
        if len(set(self.indicators)) != len(self.indicators):
            raise ValueError(f"duplicate indicator blocks in spec: {self.indicators}")
        if not self.rules:
            raise ValueError("StrategySpec needs at least one rule")
        for rule in self.rules:
            if rule.indicator not in self.indicators:
                raise ValueError(
                    f"rule references indicator {rule.indicator!r} "
                    f"not listed in {self.indicators}"
                )
        unknown = set(self.target_regimes) - set(REGIME_LABELS)
        if unknown:
            raise ValueError(f"unknown target regimes: {sorted(unknown)}")

    # -- identity (I8) -----------------------------------------------------

    def indicator_set(self) -> frozenset[str]:
        """The set of indicator blocks used (the diversity unit, WP-5.2)."""
        return frozenset(self.indicators)

    def canonical(self) -> str:
        """Canonical JSON serialisation (sorted keys) — the hash input."""
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        """Stable content hash of the full spec (pinned into manifests, I8)."""
        return hashlib.sha256(self.canonical().encode()).hexdigest()

    @property
    def key(self) -> str:
        """Short stable identity: ``name@version#hash12``."""
        return f"{self.name}@{self.version}#{self.spec_hash()[:12]}"

    def __hash__(self) -> int:
        return hash(self.spec_hash())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StrategySpec):
            return NotImplemented
        return self.canonical() == other.canonical()

    def with_params(
        self, params: Mapping[str, float], rules: Sequence[Rule] | None = None
    ) -> StrategySpec:
        """A copy with updated params (and optionally rules) — used by the GA."""
        merged = {**self.params, **{k: float(v) for k, v in params.items()}}
        return replace(
            self, params=merged, rules=tuple(rules) if rules is not None else self.rules
        )

    # -- serialisation -----------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (round-trips via ``from_dict``)."""
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "indicators": list(self.indicators),
            "rules": [r.as_dict() for r in self.rules],
            "params": {k: float(v) for k, v in sorted(self.params.items())},
            "target_regimes": list(self.target_regimes),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StrategySpec:
        """Rebuild a spec from its ``as_dict`` form."""
        return cls(
            name=str(data["name"]),
            version=str(data.get("version", "1")),
            family=str(data.get("family", "generic")),
            indicators=tuple(data.get("indicators", ())),
            rules=tuple(Rule.from_dict(r) for r in data.get("rules", ())),
            params={str(k): float(v) for k, v in dict(data.get("params", {})).items()},
            target_regimes=tuple(data.get("target_regimes", ())),
            rationale=str(data.get("rationale", "")),
        )


# ---------------------------------------------------------------------------
# The compiler: spec -> causal signals
# ---------------------------------------------------------------------------


class IndicatorStrategy:
    """Compile a :class:`StrategySpec` into a runnable, causal strategy.

    Each rule votes ``action * weight`` on every bar where its condition
    holds; the target position is the weight-normalised sum of votes,
    clipped to [-1, 1]. Warm-up NaNs never vote (flat), and every block is
    built on causal indicators, so the signal at bar *t* is a pure function
    of bars ≤ *t* (I2) and of the spec alone (I8).
    """

    def __init__(self, spec: StrategySpec, blocks: StrategyRegistry | None = None) -> None:
        """
        Args:
            spec: the strategy description to compile.
            blocks: registry to resolve building blocks from (the module
                default when omitted).

        Raises:
            KeyError: when the spec references an unregistered indicator or
                comparator.
        """
        self._registry = blocks if blocks is not None else registry
        self.spec = spec
        # Fail fast at compile time, not at signal time.
        self._blocks = {name: self._registry.indicator(name) for name in spec.indicators}
        self._comparators = {
            rule.comparator: self._registry.comparator(rule.comparator) for rule in spec.rules
        }

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Target position per bar in [-1, 1] over ``ohlcv`` (causal, I2)."""
        index = ohlcv.index
        series = {
            name: block.compute(ohlcv, self.spec.params) for name, block in self._blocks.items()
        }
        votes = pd.Series(0.0, index=index)
        total_weight = 0.0
        for rule in self.spec.rules:
            condition = self._comparators[rule.comparator].fn(
                series[rule.indicator], rule.threshold
            )
            condition = condition.fillna(False).astype(bool)  # warm-up never votes
            votes = votes + condition.astype(float) * (rule.action * rule.weight)
            total_weight += rule.weight
        return (votes / total_weight).clip(-1.0, 1.0)


def compile_spec(spec: StrategySpec, blocks: StrategyRegistry | None = None) -> IndicatorStrategy:
    """Compile a spec into a runnable :class:`Strategy` (convenience)."""
    return IndicatorStrategy(spec, blocks=blocks)


# ---------------------------------------------------------------------------
# Default building blocks — all strictly causal (I2)
# ---------------------------------------------------------------------------


def _close(ohlcv: pd.DataFrame) -> pd.Series:
    return ohlcv["close"].astype(float)


def _ind_momentum(ohlcv: pd.DataFrame, period: int = 12) -> pd.Series:
    """Simple return over ``period`` bars."""
    return ta.returns(_close(ohlcv), period)


def _ind_ema_ratio(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """Close relative to its EMA: ``close / ema - 1``."""
    return _close(ohlcv) / ta.ema(_close(ohlcv), period) - 1.0


def _ind_sma_ratio(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """Close relative to its SMA: ``close / sma - 1``."""
    return _close(ohlcv) / ta.sma(_close(ohlcv), period) - 1.0


def _ind_rsi(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """RSI rescaled from [0, 100] to [-1, 1]."""
    return (ta.rsi(_close(ohlcv), period) - 50.0) / 50.0


def _ind_macd_hist(
    ohlcv: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    """MACD histogram normalised by price."""
    slow = max(slow, fast + 1)  # keep the grammar valid for any sampled params
    frame = ta.macd(_close(ohlcv), fast=fast, slow=slow, signal=signal)
    return frame["histogram"] / _close(ohlcv)


def _ind_zscore(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rolling z-score of the close."""
    return ta.zscore(_close(ohlcv), period)


def _ind_bollinger_b(ohlcv: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.Series:
    """Bollinger %B centred on 0 (lower band -0.5, upper band +0.5)."""
    return ta.bollinger(_close(ohlcv), period, num_std)["percent_b"] - 0.5


def _ind_vol_zscore(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """Z-score of rolling volatility (volatility regime shifts)."""
    return ta.zscore(ta.rolling_volatility(_close(ohlcv), period), period)


def _ind_atr_ratio(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as a fraction of price."""
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    return ta.atr(high, low, _close(ohlcv), period) / _close(ohlcv)


def _ind_channel_pos(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """Position of close inside the rolling min/max channel, in [-0.5, 0.5]."""
    close = _close(ohlcv)
    lowest = close.rolling(period, min_periods=period).min()
    highest = close.rolling(period, min_periods=period).max()
    width = (highest - lowest).replace(0.0, np.nan)
    return (close - lowest) / width - 0.5


def _register_defaults(reg: StrategyRegistry) -> None:
    """Register the default indicator and comparator building blocks."""
    period = ParamSpec("period", 12.0, 2.0, 48.0, integer=True)
    reg.register_indicator(
        IndicatorBlock(
            "momentum", _ind_momentum, (period,),
            ParamSpec("threshold", 0.0, -0.05, 0.05), "N-bar simple return",
        )
    )
    lookback = ParamSpec("period", 20.0, 5.0, 96.0, integer=True)
    reg.register_indicator(
        IndicatorBlock(
            "ema_ratio", _ind_ema_ratio, (lookback,),
            ParamSpec("threshold", 0.0, -0.05, 0.05), "close vs EMA",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "sma_ratio", _ind_sma_ratio, (lookback,),
            ParamSpec("threshold", 0.0, -0.05, 0.05), "close vs SMA",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "rsi", _ind_rsi, (ParamSpec("period", 14.0, 5.0, 30.0, integer=True),),
            ParamSpec("threshold", 0.0, -0.8, 0.8), "RSI rescaled to [-1, 1]",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "macd_hist", _ind_macd_hist,
            (
                ParamSpec("fast", 12.0, 5.0, 18.0, integer=True),
                ParamSpec("slow", 26.0, 19.0, 48.0, integer=True),
                ParamSpec("signal", 9.0, 3.0, 15.0, integer=True),
            ),
            ParamSpec("threshold", 0.0, -0.01, 0.01), "MACD histogram / price",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "zscore", _ind_zscore, (ParamSpec("period", 20.0, 5.0, 60.0, integer=True),),
            ParamSpec("threshold", 0.0, -2.5, 2.5), "rolling z-score of close",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "bollinger_b", _ind_bollinger_b,
            (
                ParamSpec("period", 20.0, 10.0, 40.0, integer=True),
                ParamSpec("num_std", 2.0, 1.5, 3.0),
            ),
            ParamSpec("threshold", 0.0, -0.6, 0.6), "Bollinger %B centred on 0",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "vol_zscore", _ind_vol_zscore,
            (ParamSpec("period", 20.0, 10.0, 60.0, integer=True),),
            ParamSpec("threshold", 0.0, -2.5, 2.5), "z-score of rolling volatility",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "atr_ratio", _ind_atr_ratio,
            (ParamSpec("period", 14.0, 5.0, 30.0, integer=True),),
            ParamSpec("threshold", 0.01, 0.0, 0.05), "ATR as a fraction of price",
        )
    )
    reg.register_indicator(
        IndicatorBlock(
            "channel_pos", _ind_channel_pos,
            (ParamSpec("period", 20.0, 10.0, 60.0, integer=True),),
            ParamSpec("threshold", 0.0, -0.45, 0.45), "position in rolling min/max channel",
        )
    )

    reg.register_comparator(Comparator("gt", lambda s, t: s > t, "value above threshold"))
    reg.register_comparator(Comparator("lt", lambda s, t: s < t, "value below threshold"))
    reg.register_comparator(Comparator("abs_gt", lambda s, t: s.abs() > t, "|value| above"))
    reg.register_comparator(
        Comparator(
            "cross_above",
            lambda s, t: (s > t) & (s.shift(1) <= t),  # shift(1) is the past: causal (I2)
            "crosses up through threshold",
        )
    )
    reg.register_comparator(
        Comparator(
            "cross_below",
            lambda s, t: (s < t) & (s.shift(1) >= t),
            "crosses down through threshold",
        )
    )


_register_defaults(registry)
