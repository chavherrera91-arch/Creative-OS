"""The miner — keep digging for strategies, save the gold.

Each :meth:`StrategyMiner.dig` generates a fresh batch of candidate strategies
(a new seed per round, so it explores new ground), runs them through the honest
:class:`~quantos.strategy.lab.StrategyLab` (out-of-sample + Deflated-Sharpe
gate, I9), and drops the **survivors** into the :class:`StrategyVault`.
:meth:`run` repeats this on an interval — so it keeps digging while you are
away and you return to a library of the best strategies it found.

Everything is research-only (no capital, I1); each round is deterministic for a
given ``(seed, round, data)`` (I8). Data is real exchange bars when reachable,
otherwise it rotates through the synthetic scenario library and says so.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from quantos.mining.vault import GoldStrategy, StrategyVault
from quantos.scenarios.library import get_scenario, scenario_names
from quantos.strategy.generator import RandomStrategyGenerator
from quantos.strategy.lab import StrategyLab

__all__ = ["StrategyMiner"]


class StrategyMiner:
    """Dig for validated strategies on a schedule and stash the gold."""

    def __init__(
        self,
        vault: StrategyVault | None = None,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        bars: int = 400,
        n_candidates: int = 40,
        top_k: int = 6,
        min_dsr: float = 0.6,
        seed: int = 7,
        force_synthetic: bool = False,
        market: str = "crypto",
    ) -> None:
        """
        Args:
            vault: where gold is saved (a default vault when omitted).
            symbol: market to mine when using real data.
            timeframe: bar size for real data.
            bars: how many bars each dig evaluates.
            n_candidates: strategies generated per dig.
            top_k: how many can survive the lab cull per dig.
            min_dsr: honesty gate — a survivor's Deflated Sharpe floor (I9).
            seed: base RNG seed; each round adds to it to explore new specs.
            force_synthetic: never touch the network (rotate scenarios).
        """
        self.vault = vault if vault is not None else StrategyVault()
        self.symbol = symbol
        self.timeframe = timeframe
        self.bars = bars
        self.n_candidates = n_candidates
        self.top_k = top_k
        self.min_dsr = min_dsr
        self.seed = seed
        self.force_synthetic = force_synthetic
        self.market = market

    # -- data ----------------------------------------------------------------
    def _load_ohlcv(self, round_index: int) -> tuple[pd.DataFrame, str]:
        """Real market bars when reachable, else a rotating synthetic scenario."""
        if not self.force_synthetic:
            if self.market == "forex":
                from quantos.data.forex import fetch_forex_ohlcv

                frame, source = fetch_forex_ohlcv(self.symbol, self.timeframe, self.bars)
                if source == "yfinance":
                    return frame, "yfinance"
            else:
                from quantos.config import Settings
                from quantos.data.collector import DataCollector

                settings = Settings(
                    **{  # type: ignore[arg-type]
                        **Settings.from_env().as_dict(),
                        "symbol": self.symbol,
                        "timeframe": self.timeframe,
                        "bars": self.bars,
                    }
                )
                collector = DataCollector(settings=settings, force_synthetic=False)
                frame = collector.fetch_ohlcv()
                if collector.last_source == "ccxt":
                    return frame, "ccxt"
        names = scenario_names()
        scenario = get_scenario(names[round_index % len(names)])
        return scenario.generate(self.seed + round_index), scenario.name

    def _generate(self, seed: int) -> list:
        """Generate a batch, backing off if the grammar can't fill the request.

        The generator can only build so many *distinct, diverse* strategies
        (~130 with the current families); asking for more raises rather than
        repeating. Rather than lose the round, we step down to the largest
        batch the grammar can honestly produce.
        """
        from quantos.strategy.generator import GenerationError

        n = self.n_candidates
        while True:
            try:
                return RandomStrategyGenerator().generate(n, seed=seed, diversity=0.5)
            except GenerationError:
                if n <= 8:
                    raise
                n = int(n * 0.75)

    # -- one dig -------------------------------------------------------------
    def dig(self, round_index: int = 0) -> dict[str, Any]:
        """Generate, test, and stash survivors for one round; return a summary."""
        ohlcv, source = self._load_ohlcv(round_index)
        specs = self._generate(self.seed + round_index)
        result = StrategyLab(top_k=self.top_k, min_dsr=self.min_dsr, symbol=self.symbol).run(
            specs, ohlcv
        )
        finds = [
            GoldStrategy(
                spec=r.spec.as_dict(),
                spec_hash=r.spec.spec_hash(),
                family=r.spec.family,
                name=r.spec.name,
                oos_sharpe=round(float(r.oos_metrics.get("sharpe", 0.0)), 4),
                deflated_sharpe=round(float(r.validation.get("deflated_sharpe", 0.0)), 4),
                regime=result.tested_regime,
                found_round=round_index,
                source=source,
            )
            for r in result.records
            if r.survived
        ]
        new = self.vault.add(finds)
        return {
            "round": round_index,
            "source": source,
            "regime": result.tested_regime,
            "tested": len(specs),
            "gold_found": len(finds),
            "new_in_vault": new,
            "vault_size": len(self.vault),
        }

    # -- the loop ------------------------------------------------------------
    def run(
        self,
        rounds: int | None = None,
        interval_seconds: float = 1800.0,
        on_round: Callable[[dict[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Keep digging. ``rounds=None`` runs forever; returns rounds completed.

        A failing round never kills the loop — mining is best-effort and must
        survive a transient data hiccup (I6). ``sleep`` is injectable so tests
        never actually wait.
        """
        completed = 0
        round_index = 0
        while rounds is None or round_index < rounds:
            try:
                summary = self.dig(round_index)
                if on_round is not None:
                    on_round(summary)
                completed += 1
            except Exception as exc:  # noqa: BLE001 - a bad round must not stop mining
                if on_round is not None:
                    on_round({"round": round_index, "error": str(exc)})
            round_index += 1
            if rounds is None or round_index < rounds:
                sleep(interval_seconds)
        return completed
