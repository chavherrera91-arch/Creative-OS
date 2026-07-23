"""Live paper trading — a demo account on real prices with fake money.

Each :meth:`LivePaperTrader.step` pulls the **latest real bars** from the
exchange (read-only ccxt via :class:`DataCollector`; deterministic synthetic
fallback when offline, I6), asks the Investment Committee to decide, and routes
the decision through the paper execution engine. **No real capital ever moves**
— the engine refuses any non-paper broker (invariant I1). State is persisted to
a JSON file so the demo account accumulates across steps and restarts.

This is the "demo account" of classic trading platforms: real, current market
data; real-time decisions; but the money is fictitious.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantos.committee.committee import default_committee
from quantos.config import Settings
from quantos.data.collector import DataCollector, synthetic_channels
from quantos.data.models import MarketSnapshot
from quantos.execution.interfaces import PaperExecutionEngine
from quantos.paper.broker import PaperBroker

__all__ = ["LivePaperTrader"]


class LivePaperTrader:
    """Drive one live paper-trading step and persist the demo account."""

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        bars: int = 200,
        cash: float = 100_000.0,
        state_path: str | Path | None = None,
        force_synthetic: bool = False,
    ) -> None:
        """
        Args:
            symbol: market to trade (e.g. ``"BTC/USDT"``).
            timeframe: bar size requested from the exchange.
            bars: how many recent bars to pull for the committee's context.
            cash: starting (fake) equity.
            state_path: JSON file the demo account is saved to; a per-symbol
                file under the home directory by default.
            force_synthetic: never touch the network (used by tests, I6).
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.bars = bars
        self.cash = cash
        self.force_synthetic = force_synthetic
        self.state_path = Path(state_path) if state_path else self._default_state_path(symbol)

    @staticmethod
    def _default_state_path(symbol: str) -> Path:
        safe = symbol.replace("/", "-")
        return Path.home() / "quantos" / f"live-demo-{safe}.json"

    # -- state ---------------------------------------------------------------
    def account(self) -> dict[str, Any]:
        """The current demo account (creates a fresh one on first use)."""
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {
            "symbol": self.symbol,
            "cash": self.cash,
            "positions": {},
            "n_trades": 0,
            "history": [],  # [{as_of, price, equity, direction, approved, source}]
        }

    def reset(self) -> None:
        """Wipe the demo account back to the starting cash."""
        self.state_path.unlink(missing_ok=True)

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, default=str))

    # -- the live step -------------------------------------------------------
    def step(self) -> dict[str, Any]:
        """Pull the latest bars, decide, paper-execute, persist; return a summary."""
        state = self.account()

        settings = Settings(
            **{  # type: ignore[arg-type]
                **Settings.from_env().as_dict(),
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "bars": self.bars,
            }
        )
        collector = DataCollector(settings=settings, force_synthetic=self.force_synthetic)
        ohlcv = collector.fetch_ohlcv()
        source = collector.last_source
        price = float(ohlcv["close"].iloc[-1])
        as_of = str(ohlcv.index[-1])

        # Full analyst panel: real prices + (simulated) macro/sentiment channels.
        channels = synthetic_channels(self.symbol)
        snapshot = MarketSnapshot(self.symbol, self.timeframe, ohlcv, **channels)
        decision = default_committee(settings).deliberate(snapshot)

        broker = PaperBroker(
            cash=float(state["cash"]),
            fee_bps=settings.fee_bps,
            slippage_bps=settings.slippage_bps,
        )
        broker.positions = {k: float(v) for k, v in state["positions"].items()}
        engine = PaperExecutionEngine(broker=broker, settings=settings)
        trade = engine.execute(decision, price=price)

        equity = broker.equity({self.symbol: price})
        state["cash"] = broker.cash
        state["positions"] = dict(broker.positions)
        state["n_trades"] = int(state["n_trades"]) + (1 if trade is not None else 0)
        state["history"].append(
            {
                "as_of": as_of,
                "price": round(price, 2),
                "equity": round(equity, 2),
                "direction": decision.direction.value,
                "approved": decision.approved,
                "source": source,
            }
        )
        self._save(state)

        return {
            "as_of": as_of,
            "price": price,
            "source": source,
            "direction": decision.direction.value,
            "approved": decision.approved,
            "traded": trade is not None,
            "equity": equity,
            "position": broker.position(self.symbol),
            "is_paper": broker.is_paper,
        }
