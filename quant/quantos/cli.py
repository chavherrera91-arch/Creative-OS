"""Command-line interface.

    quantos decide      --symbol BTC/USDT --timeframe 1h
    quantos backtest    --symbol BTC/USDT --bars 1500 --step 6
    quantos walkforward --symbol BTC/USDT --bars 2000
    quantos montecarlo  --symbol BTC/USDT --bars 1500 --sims 2000
    quantos paper       --symbol BTC/USDT --bars 1500 --step 6

All commands run offline against synthetic data when ``ccxt`` is unavailable.
Nothing here can place a real order.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from quantos.backtest.engine import backtest, committee_signals
from quantos.backtest.monte_carlo import monte_carlo
from quantos.backtest.walk_forward import walk_forward
from quantos.committee.committee import default_committee
from quantos.config import load_settings
from quantos.data.collector import DataCollector
from quantos.execution.interfaces import PaperExecutionEngine
from quantos.explain.explainer import explain_decision
from quantos.paper.broker import PaperBroker


def _collector() -> DataCollector:
    return DataCollector(source=load_settings().data_source)


def cmd_decide(args) -> None:
    collector = _collector()
    snapshot = collector.snapshot(args.symbol, args.timeframe, args.bars)
    decision = default_committee().deliberate(snapshot)
    if args.json:
        print(json.dumps(decision.as_dict(), indent=2, default=str))
    else:
        print(explain_decision(decision))


def cmd_backtest(args) -> None:
    collector = _collector()
    ohlcv = collector.fetch_ohlcv(args.symbol, args.timeframe, args.bars)
    committee = default_committee()
    positions = committee_signals(
        committee, ohlcv, symbol=args.symbol, timeframe=args.timeframe,
        warmup=args.warmup, step=args.step,
    )
    result = backtest(ohlcv, positions)
    print(json.dumps(result.summary(), indent=2))


def cmd_walkforward(args) -> None:
    collector = _collector()
    ohlcv = collector.fetch_ohlcv(args.symbol, args.timeframe, args.bars)
    committee = default_committee()

    def signal_fn(window: pd.DataFrame, _params: dict) -> pd.Series:
        return committee_signals(
            committee, window, symbol=args.symbol, timeframe=args.timeframe,
            warmup=min(args.warmup, max(20, len(window) // 3)), step=args.step,
        )

    result = walk_forward(ohlcv, signal_fn, n_folds=args.folds)
    print(json.dumps(result.as_dict(), indent=2, default=str))


def cmd_montecarlo(args) -> None:
    collector = _collector()
    ohlcv = collector.fetch_ohlcv(args.symbol, args.timeframe, args.bars)
    committee = default_committee()
    positions = committee_signals(
        committee, ohlcv, symbol=args.symbol, timeframe=args.timeframe,
        warmup=args.warmup, step=args.step,
    )
    result = backtest(ohlcv, positions)
    mc = monte_carlo(result.returns, n_sims=args.sims)
    print(json.dumps(mc.as_dict(), indent=2))


def cmd_paper(args) -> None:
    collector = _collector()
    ohlcv = collector.fetch_ohlcv(args.symbol, args.timeframe, args.bars)
    committee = default_committee()
    broker = PaperBroker(cash=args.cash)
    engine = PaperExecutionEngine(broker)

    for i in range(args.warmup, len(ohlcv), args.step):
        window = ohlcv.iloc[: i + 1]
        from quantos.data.models import MarketSnapshot

        snapshot = MarketSnapshot(args.symbol, args.timeframe, window)
        decision = committee.deliberate(snapshot)
        engine.execute(decision, snapshot.last_price)

    mark = float(ohlcv["close"].iloc[-1])
    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "trades": len(broker.trades),
                "final_position": broker.position,
                "equity": round(broker.equity(mark), 2),
                "pnl": round(broker.pnl(mark), 2),
                "paper_trading": True,
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantos", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--symbol", default="BTC/USDT")
        p.add_argument("--timeframe", default="1h")
        p.add_argument("--bars", type=int, default=1000)

    p = sub.add_parser("decide", help="Run the committee once and explain it")
    common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("backtest", help="Committee-driven backtest")
    common(p)
    p.add_argument("--warmup", type=int, default=100)
    p.add_argument("--step", type=int, default=6)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("walkforward", help="Walk-forward out-of-sample evaluation")
    common(p)
    p.add_argument("--warmup", type=int, default=60)
    p.add_argument("--step", type=int, default=6)
    p.add_argument("--folds", type=int, default=5)
    p.set_defaults(func=cmd_walkforward)

    p = sub.add_parser("montecarlo", help="Monte Carlo robustness of the backtest")
    common(p)
    p.add_argument("--warmup", type=int, default=100)
    p.add_argument("--step", type=int, default=6)
    p.add_argument("--sims", type=int, default=1000)
    p.set_defaults(func=cmd_montecarlo)

    p = sub.add_parser("paper", help="Paper-trade the committee (no real money)")
    common(p)
    p.add_argument("--warmup", type=int, default=100)
    p.add_argument("--step", type=int, default=6)
    p.add_argument("--cash", type=float, default=10_000.0)
    p.set_defaults(func=cmd_paper)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
