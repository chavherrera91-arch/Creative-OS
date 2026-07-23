"""Market Simulator (module 21) — replay a scenario bar-by-bar, as if live.

The M4 scenario library generates a whole path at once for vectorised
backtests; this replays that path **one bar at a time through the live
pipeline** (regime → meta → committee → paper broker), so the platform can be
watched reacting in real time to a ``COVID_CRASH`` or an ``ETF_RALLY``.

Each step forms its snapshot from the prefix ``bars ≤ t`` only — the decision
never sees a future bar (I2) — and every fill goes through a paper broker
(``is_paper`` is asserted, no capital, I1). The whole replay is a pure
function of ``(scenario, seed)`` (I8): same inputs, same step log.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from quantos.committee.base import Direction
from quantos.committee.decision import CommitteeDecision
from quantos.data.models import MarketSnapshot
from quantos.memory.archive import DecisionArchive
from quantos.paper.broker import PaperBroker
from quantos.pipeline import ResearchPipeline, research_pipeline
from quantos.scenarios.library import Scenario, get_scenario

__all__ = ["MarketSimulator", "ReplayResult", "SimStep"]

_SIDE = {1: "buy", -1: "sell"}


@dataclass
class SimStep:
    """One replayed bar's decision and its effect on the paper book (I4).

    Attributes:
        index: bar index in the scenario path.
        as_of: bar timestamp (ISO).
        price: decision-time price (the bar's close).
        direction: the committee's call at this bar.
        approved: whether the decision was approved.
        blocked_by_risk: whether the risk veto fired.
        regime_label: the classified regime at this bar.
        position: signed paper position after acting.
        equity: paper equity marked at this bar's price.
    """

    index: int
    as_of: str
    price: float
    direction: str
    approved: bool
    blocked_by_risk: bool
    regime_label: str
    position: float
    equity: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "index": self.index,
            "as_of": self.as_of,
            "price": self.price,
            "direction": self.direction,
            "approved": self.approved,
            "blocked_by_risk": self.blocked_by_risk,
            "regime_label": self.regime_label,
            "position": self.position,
            "equity": self.equity,
        }


@dataclass
class ReplayResult:
    """The full replay: every step plus the final paper book (I4/I8).

    Attributes:
        scenario: the replayed scenario's name.
        seed: the seed the path was generated with.
        steps: the per-bar step log.
        final_equity: paper equity at the last replayed bar.
        n_trades: number of paper fills.
        account: the paper broker's closing summary.
    """

    scenario: str
    seed: int
    steps: list[SimStep] = field(default_factory=list)
    final_equity: float = 0.0
    n_trades: int = 0
    account: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "scenario": self.scenario,
            "seed": self.seed,
            "steps": [s.as_dict() for s in self.steps],
            "final_equity": self.final_equity,
            "n_trades": self.n_trades,
            "account": self.account,
        }


class MarketSimulator:
    """Replay scenarios bar-by-bar through the live pipeline and paper broker."""

    def __init__(
        self,
        pipeline: ResearchPipeline | None = None,
        *,
        warmup: int = 60,
        step: int = 4,
        trade_qty: float = 1.0,
        cash: float = 100_000.0,
        archive: DecisionArchive | None = None,
    ) -> None:
        """
        Args:
            pipeline: the §4 stack to drive (default :func:`research_pipeline`).
            warmup: bars to stay flat while indicators warm up.
            step: deliberate every ``step`` bars (the clock's tick size).
            trade_qty: paper quantity per unit of target direction.
            cash: starting paper cash for each replay.
            archive: optional Decision Archive every decision is recorded into.
        """
        self.pipeline = pipeline if pipeline is not None else research_pipeline()
        self.warmup = warmup
        self.step = step
        self.trade_qty = trade_qty
        self.cash = cash
        self.archive = archive

    def stream(self, scenario: Scenario | str, seed: int | None = None) -> Iterator[SimStep]:
        """Yield each bar's :class:`SimStep` as the replay advances (as-if live).

        The paper broker lives on ``self._broker`` for the duration of the
        stream; fills happen as each step is yielded, so a consumer sees the
        book evolve in real time.
        """
        if isinstance(scenario, str):
            scenario = get_scenario(scenario)
        ohlcv = scenario.generate(seed)
        broker = PaperBroker(cash=self.cash)
        assert broker.is_paper, "MarketSimulator only ever drives a paper broker (I1)"
        self._broker = broker

        n = len(ohlcv)
        for t in range(self.warmup, n, self.step):
            prefix = ohlcv.iloc[: t + 1]
            snapshot = MarketSnapshot(
                symbol=scenario.symbol, timeframe=scenario.timeframe, ohlcv=prefix
            )
            decision = self.pipeline.decide(snapshot)
            if self.archive is not None:
                self.archive.record(decision)
            price = float(prefix["close"].iloc[-1])
            self._act(broker, scenario.symbol, decision, price)
            yield SimStep(
                index=t,
                as_of=str(prefix.index[-1]),
                price=price,
                direction=decision.direction.value,
                approved=decision.approved,
                blocked_by_risk=decision.blocked_by_risk,
                regime_label=str((decision.regime or {}).get("label", "")),
                position=broker.position(scenario.symbol),
                equity=broker.equity({scenario.symbol: price}),
            )

    def replay(self, scenario: Scenario | str, seed: int | None = None) -> ReplayResult:
        """Run the whole replay and collect it into a :class:`ReplayResult`."""
        if isinstance(scenario, str):
            scenario = get_scenario(scenario)
        used_seed = scenario._seed(seed)
        steps = list(self.stream(scenario, seed))
        broker = self._broker
        last_price = steps[-1].price if steps else 0.0
        return ReplayResult(
            scenario=scenario.name,
            seed=used_seed,
            steps=steps,
            final_equity=broker.equity({scenario.symbol: last_price}),
            n_trades=len(broker.trades),
            account=broker.as_dict(),
        )

    # -- internals ------------------------------------------------------------
    def _act(
        self, broker: PaperBroker, symbol: str, decision: CommitteeDecision, price: float
    ) -> None:
        """Move the paper position toward the decision's target (no look-ahead)."""
        target = 0.0
        if decision.approved and decision.direction is Direction.LONG:
            target = self.trade_qty
        elif decision.approved and decision.direction is Direction.SHORT:
            target = -self.trade_qty
        delta = target - broker.position(symbol)
        if delta == 0.0:
            return
        side = _SIDE[1] if delta > 0 else _SIDE[-1]
        broker.submit(
            symbol,
            side,
            abs(delta),
            price,
            as_of=str(decision.as_of),
            dossier=decision.as_dict(),
            regime=decision.regime,
        )
