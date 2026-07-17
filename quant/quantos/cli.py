"""quantos command-line interface.

Five research commands, all offline-capable and reproducible for a fixed seed::

    python -m quantos.cli decide      --symbol BTC/USDT --bars 400
    python -m quantos.cli backtest    --symbol BTC/USDT --bars 400
    python -m quantos.cli walkforward --symbol BTC/USDT --bars 600
    python -m quantos.cli montecarlo  --symbol BTC/USDT --bars 400
    python -m quantos.cli paper       --symbol BTC/USDT --bars 400

Without ccxt/network the collector transparently uses the deterministic
synthetic generator (I6); nothing here can ever place a live order (I1).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

import pandas as pd

from quantos.backtest.engine import backtest, committee_signals
from quantos.backtest.monte_carlo import monte_carlo
from quantos.backtest.walk_forward import walk_forward
from quantos.committee.committee import default_committee
from quantos.config import Settings
from quantos.data.collector import DataCollector
from quantos.execution.interfaces import build_execution_engine
from quantos.explain.explainer import explain_decision

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quantos",
        description="AI quant research platform — investment committee, "
        "validation funnel, paper trading only (I1).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--symbol", default=None, help="pair, e.g. BTC/USDT")
        p.add_argument("--timeframe", default=None, help="bar timeframe, e.g. 1h")
        p.add_argument("--bars", type=int, default=None, help="number of bars")
        p.add_argument("--seed", type=int, default=None, help="random seed (I8)")
        p.add_argument(
            "--synthetic",
            action="store_true",
            help="force the deterministic synthetic data path (never touch the network)",
        )
        p.add_argument(
            "--channels",
            action="store_true",
            help="attach deterministic synthetic macro/sentiment/on-chain channels",
        )

    p_decide = sub.add_parser("decide", help="run the committee once, print the full explanation")
    common(p_decide)

    p_bt = sub.add_parser("backtest", help="committee-driven backtest with baselines")
    common(p_bt)
    p_bt.add_argument("--warmup", type=int, default=60)
    p_bt.add_argument("--step", type=int, default=5, help="deliberate every N bars")
    p_bt.add_argument("--fee-bps", type=float, default=None)
    p_bt.add_argument("--slippage-bps", type=float, default=None)

    p_wf = sub.add_parser("walkforward", help="out-of-sample walk-forward folds")
    common(p_wf)
    p_wf.add_argument("--folds", type=int, default=4)
    p_wf.add_argument("--min-train", type=int, default=100)
    p_wf.add_argument("--warmup", type=int, default=60)
    p_wf.add_argument("--step", type=int, default=5)

    p_mc = sub.add_parser("montecarlo", help="Monte Carlo resampling of the backtest")
    common(p_mc)
    p_mc.add_argument("--sims", type=int, default=500)
    p_mc.add_argument("--warmup", type=int, default=60)
    p_mc.add_argument("--step", type=int, default=5)

    p_paper = sub.add_parser("paper", help="decide, then execute on the paper broker")
    common(p_paper)
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    base = Settings.from_env()
    overrides: dict[str, object] = {}
    if args.symbol:
        overrides["symbol"] = args.symbol
    if args.timeframe:
        overrides["timeframe"] = args.timeframe
    if args.bars:
        overrides["bars"] = args.bars
    if args.seed is not None:
        overrides["seed"] = args.seed
    if getattr(args, "fee_bps", None) is not None:
        overrides["fee_bps"] = args.fee_bps
    if getattr(args, "slippage_bps", None) is not None:
        overrides["slippage_bps"] = args.slippage_bps
    return Settings(**{**base.as_dict(), **overrides})  # type: ignore[arg-type]


def _ohlcv(settings: Settings, args: argparse.Namespace) -> pd.DataFrame:
    collector = DataCollector(settings=settings, force_synthetic=args.synthetic)
    frame = collector.fetch_ohlcv()
    print(f"data source: {collector.last_source} ({len(frame)} bars of {settings.symbol})")
    return frame


def _print_json(title: str, payload: object) -> None:
    print(f"\n--- {title} ---")
    print(json.dumps(payload, indent=2, default=str))


def _cmd_decide(args: argparse.Namespace) -> int:
    settings = _settings(args)
    collector = DataCollector(settings=settings, force_synthetic=args.synthetic)
    snapshot = collector.snapshot(include_channels=args.channels)
    print(f"data source: {collector.last_source}")
    decision = default_committee(settings).deliberate(snapshot)
    print(explain_decision(decision))
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    settings = _settings(args)
    ohlcv = _ohlcv(settings, args)
    positions = committee_signals(
        ohlcv,
        default_committee(settings),
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        warmup=args.warmup,
        step=args.step,
    )
    result = backtest(
        ohlcv, positions, fee_bps=settings.fee_bps, slippage_bps=settings.slippage_bps
    )
    _print_json("strategy metrics", result.metrics)
    _print_json("baselines (must beat both to claim an edge)", result.baselines)
    print(f"\ntrades: {result.n_trades} | final equity: {float(result.equity.iloc[-1]):.4f}")
    return 0


def _make_signal_fn(settings: Settings, warmup: int, step: int) -> object:
    committee = default_committee(settings)

    def signal_fn(prefix: pd.DataFrame) -> pd.Series:
        return committee_signals(
            prefix,
            committee,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            warmup=warmup,
            step=step,
        )

    return signal_fn


def _cmd_walkforward(args: argparse.Namespace) -> int:
    settings = _settings(args)
    ohlcv = _ohlcv(settings, args)
    result = walk_forward(
        ohlcv,
        _make_signal_fn(settings, args.warmup, args.step),  # type: ignore[arg-type]
        n_folds=args.folds,
        min_train=args.min_train,
        fee_bps=settings.fee_bps,
        slippage_bps=settings.slippage_bps,
    )
    for fold in result.folds:
        print(
            f"fold {fold.fold}: test {fold.test_start} -> {fold.test_end} "
            f"({fold.n_test_bars} bars) sharpe={fold.metrics['sharpe']:.2f} "
            f"return={fold.metrics['total_return']:+.2%}"
        )
    _print_json("aggregate out-of-sample metrics", result.oos_metrics)
    _print_json("baselines", result.baselines)
    return 0


def _cmd_montecarlo(args: argparse.Namespace) -> int:
    settings = _settings(args)
    ohlcv = _ohlcv(settings, args)
    positions = committee_signals(
        ohlcv,
        default_committee(settings),
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        warmup=args.warmup,
        step=args.step,
    )
    result = backtest(
        ohlcv, positions, fee_bps=settings.fee_bps, slippage_bps=settings.slippage_bps
    )
    mc = monte_carlo(result.returns, n_sims=args.sims, seed=settings.seed)
    _print_json("monte carlo", mc.as_dict())
    return 0


def _cmd_paper(args: argparse.Namespace) -> int:
    settings = _settings(args)
    collector = DataCollector(settings=settings, force_synthetic=args.synthetic)
    snapshot = collector.snapshot(include_channels=args.channels)
    decision = default_committee(settings).deliberate(snapshot)
    print(explain_decision(decision))

    engine = build_execution_engine(live=False, settings=settings)  # paper only (I1)
    record = engine.execute(decision)
    if record is None:
        print("\nPAPER EXECUTION: no trade — the decision did not clear the risk gate.")
    else:
        summary = record.as_dict()
        summary["dossier"] = {"reasons": summary["dossier"].get("reasons", [])}
        _print_json("PAPER TRADE RECORD (dossier abridged)", summary)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = _build_parser().parse_args(argv)
    handlers = {
        "decide": _cmd_decide,
        "backtest": _cmd_backtest,
        "walkforward": _cmd_walkforward,
        "montecarlo": _cmd_montecarlo,
        "paper": _cmd_paper,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
