"""Scenario library (module 13, M4 scope).

Named historical-style market regimes — ``COVID_CRASH``, ``FTX``,
``ETF_RALLY``, ``BEAR_2022``, ``BULL_2021`` — as **parameterised synthetic
generators**: each scenario is a sequence of phases (bars, drift, vol) whose
path is a pure function of ``(scenario, seed)`` (invariant I8). No historical
data is shipped or fetched (I6); the shapes are stylised reproductions.

Each scenario labels its **ground-truth regime** on a designated core phase,
so the Market Regime Engine can be scored against it: the classifier, shown
only the bars up to the end of the core phase (I2), should recover the label.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quantos.data.models import MarketSnapshot
from quantos.regime.base import REGIME_LABELS

__all__ = ["SCENARIOS", "Phase", "Scenario", "get_scenario", "scenario_names"]

_SCENARIO_EPOCH = "2024-01-01"  # fixed anchor — never a wall clock (I8)


@dataclass(frozen=True)
class Phase:
    """One homogeneous stretch of a scenario.

    Attributes:
        bars: number of bars in the phase.
        drift: per-bar mean log-return.
        vol: per-bar log-return volatility.
        name: human label for the phase (audit/reporting).
    """

    bars: int
    drift: float
    vol: float
    name: str = ""


@dataclass(frozen=True)
class Scenario:
    """A named, parameterised synthetic market regime.

    Attributes:
        name: scenario identifier, e.g. ``"COVID_CRASH"``.
        description: what historical episode the shape is styled after.
        regime_label: ground-truth regime on the core phase (one of
            :data:`~quantos.regime.base.REGIME_LABELS`).
        phases: the phase sequence that builds the path.
        core_phase: index into ``phases`` of the segment the label describes.
        seed: default seed; the path is a pure function of (scenario, seed).
        symbol: symbol label stamped on generated snapshots.
        timeframe: bar timeframe of the generated path.
        start_price: first open.
    """

    name: str
    description: str
    regime_label: str
    phases: tuple[Phase, ...]
    core_phase: int
    seed: int = 42
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start_price: float = 50_000.0

    def __post_init__(self) -> None:
        if self.regime_label not in REGIME_LABELS:
            raise ValueError(f"unknown regime label {self.regime_label!r}")
        if not 0 <= self.core_phase < len(self.phases):
            raise ValueError(f"core_phase {self.core_phase} out of range")

    @property
    def bars(self) -> int:
        """Total number of bars across all phases."""
        return sum(phase.bars for phase in self.phases)

    @property
    def core_end(self) -> int:
        """Bar count up to and including the end of the core phase."""
        return sum(phase.bars for phase in self.phases[: self.core_phase + 1])

    def _seed(self, seed: int | None) -> int:
        base = self.seed if seed is None else seed
        return (zlib.crc32(self.name.encode()) ^ base) & 0xFFFFFFFF

    def generate(self, seed: int | None = None) -> pd.DataFrame:
        """Generate the scenario's OHLCV path (deterministic per seed, I8).

        Returns:
            Frame indexed by UTC timestamps with ``open/high/low/close/volume``;
            volume swells with each phase's volatility (stress = turnover).
        """
        rng = np.random.default_rng(self._seed(seed))
        drift = np.concatenate([np.full(p.bars, p.drift) for p in self.phases])
        vol = np.concatenate([np.full(p.bars, p.vol) for p in self.phases])
        n = len(drift)

        log_ret = rng.normal(0.0, 1.0, size=n) * vol + drift
        close = self.start_price * np.exp(np.cumsum(log_ret))
        open_ = np.concatenate([[self.start_price], close[:-1]])
        wick = np.abs(rng.normal(0.0, 0.5, size=n)) * vol * close
        high = np.maximum(open_, close) + wick
        low = np.minimum(open_, close) - wick
        volume = rng.lognormal(mean=4.0, sigma=0.3, size=n) * (1.0 + 40.0 * vol)

        index = pd.date_range(_SCENARIO_EPOCH, periods=n, freq="1h", tz="UTC")
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=index,
        )

    def core_snapshot(self, seed: int | None = None) -> MarketSnapshot:
        """Snapshot ending at the core phase's last bar — only bars ≤ t (I2).

        This is the view against which the Regime Engine is scored: it must
        recover :attr:`regime_label` from exactly this history.
        """
        ohlcv = self.generate(seed).iloc[: self.core_end]
        return MarketSnapshot(symbol=self.symbol, timeframe=self.timeframe, ohlcv=ohlcv)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable description (pinned into run manifests, I8)."""
        return {
            "name": self.name,
            "description": self.description,
            "regime_label": self.regime_label,
            "phases": [
                {"bars": p.bars, "drift": p.drift, "vol": p.vol, "name": p.name}
                for p in self.phases
            ],
            "core_phase": self.core_phase,
            "seed": self.seed,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_price": self.start_price,
        }


def _build_library() -> dict[str, Scenario]:
    return {
        scenario.name: scenario
        for scenario in (
            Scenario(
                name="COVID_CRASH",
                description="March-2020 style: a calm grind, then a violent "
                "liquidity-cascade crash, then a sharp V-shaped rebound.",
                regime_label="CRISIS",
                phases=(
                    Phase(200, 0.0005, 0.004, "calm grind"),
                    Phase(40, -0.02, 0.03, "cascade crash"),
                    Phase(120, 0.004, 0.012, "V rebound"),
                ),
                core_phase=1,
            ),
            Scenario(
                name="FTX",
                description="November-2022 style: an uneasy drift, an exchange "
                "collapse air-pocket, then a shell-shocked aftermath.",
                regime_label="CRISIS",
                phases=(
                    Phase(180, 0.0, 0.006, "uneasy drift"),
                    Phase(30, -0.025, 0.035, "collapse"),
                    Phase(60, -0.001, 0.015, "aftermath"),
                ),
                core_phase=1,
            ),
            Scenario(
                name="ETF_RALLY",
                description="Early-2024 style: quiet accumulation, then a steady "
                "institutional-inflow uptrend on stable volatility.",
                regime_label="TREND_UP",
                phases=(
                    Phase(120, 0.0002, 0.006, "accumulation"),
                    Phase(200, 0.0035, 0.005, "inflow rally"),
                ),
                core_phase=1,
            ),
            Scenario(
                name="BEAR_2022",
                description="2022 style: a distribution top rolling into a long, "
                "orderly grind lower as liquidity tightens.",
                regime_label="TREND_DOWN",
                phases=(
                    Phase(60, 0.0, 0.008, "distribution top"),
                    Phase(300, -0.003, 0.006, "grind lower"),
                ),
                core_phase=1,
            ),
            Scenario(
                name="BULL_2021",
                description="2021 style: an accumulation base breaking into an "
                "exuberant, high-participation bull trend.",
                regime_label="TREND_UP",
                phases=(
                    Phase(80, 0.0005, 0.006, "base"),
                    Phase(250, 0.004, 0.008, "bull trend"),
                ),
                core_phase=1,
            ),
        )
    }


#: The named scenario library (BUILD_PLAN WP-4.5).
SCENARIOS: dict[str, Scenario] = _build_library()


def scenario_names() -> list[str]:
    """The available scenario names, sorted."""
    return sorted(SCENARIOS)


def get_scenario(name: str) -> Scenario:
    """Look a scenario up by name.

    Raises:
        KeyError: with the available names, when the scenario is unknown.
    """
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {name!r}; available: {scenario_names()}") from exc
