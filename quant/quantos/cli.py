"""quantos command-line interface.

Research commands (M1) plus Data Lake commands (M2), all offline-capable and
reproducible for a fixed seed::

    python -m quantos.cli decide      --symbol BTC/USDT --bars 400
    python -m quantos.cli decide      --symbol BTC/USDT --from-lake
    python -m quantos.cli backtest    --symbol BTC/USDT --bars 400
    python -m quantos.cli walkforward --symbol BTC/USDT --bars 600
    python -m quantos.cli montecarlo  --symbol BTC/USDT --bars 400
    python -m quantos.cli paper       --symbol BTC/USDT --bars 400
    python -m quantos.cli ingest      --symbol BTC/USDT
    python -m quantos.cli catalog
    python -m quantos.cli health

Without ccxt/network every connector transparently uses its deterministic
synthetic mode (I6); nothing here can ever place a live order (I1).
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
from quantos.data.lake import DataLake
from quantos.data.store.duckdb_store import DuckDBStore
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

    def lake_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--lake-root",
            default=None,
            help="Data Lake directory (default: QUANTOS_LAKE_ROOT or ./.quantos-lake)",
        )

    p_decide = sub.add_parser("decide", help="run the committee once, print the full explanation")
    common(p_decide)
    lake_opts(p_decide)
    p_decide.add_argument(
        "--from-lake",
        action="store_true",
        help="build the snapshot from the curated Data Lake (all channels, 0 abstentions)",
    )

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

    p_ingest = sub.add_parser("ingest", help="ingest every registered connector into the lake")
    common(p_ingest)
    lake_opts(p_ingest)
    p_ingest.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="restrict to these connector categories (default: all)",
    )
    p_ingest.add_argument(
        "--repair-gaps",
        action="store_true",
        help="also detect and backfill cadence gaps after ingesting",
    )

    p_catalog = sub.add_parser("catalog", help="list the lake's datasets, schemas and coverage")
    lake_opts(p_catalog)

    p_health = sub.add_parser("health", help="per-connector freshness, success rate and circuits")
    lake_opts(p_health)
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


def _build_lake(args: argparse.Namespace, settings: Settings | None = None) -> DataLake:
    """A DataLake persisted under ``--lake-root`` (env/default otherwise)."""
    settings = settings or Settings.from_env()
    root = getattr(args, "lake_root", None) or settings.lake_root
    return DataLake(store=DuckDBStore(root=root), settings=settings)


def _cmd_decide(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if args.from_lake:
        lake = _build_lake(args, settings)
        mode = "synthetic" if args.synthetic else "auto"
        try:
            snapshot = lake.snapshot(settings.symbol, settings.timeframe)
        except ValueError:
            print("lake holds no curated data yet — ingesting first")
            lake.ingest(settings.symbol, settings.timeframe, mode=mode)
            snapshot = lake.snapshot(settings.symbol, settings.timeframe)
        print(
            f"data source: lake ({snapshot.bars} curated bars, "
            f"all channels as-of {snapshot.as_of})"
        )
    else:
        collector = DataCollector(settings=settings, force_synthetic=args.synthetic)
        snapshot = collector.snapshot(include_channels=args.channels)
        print(f"data source: {collector.last_source}")
    decision = default_committee(settings).deliberate(snapshot)
    print(explain_decision(decision))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    settings = _settings(args)
    lake = _build_lake(args, settings)
    mode = "synthetic" if args.synthetic else "auto"
    reports = lake.ingest(
        settings.symbol, settings.timeframe, categories=args.categories, mode=mode
    )
    print(f"lake root: {getattr(args, 'lake_root', None) or settings.lake_root}")
    for name, report in reports.items():
        status = "ok" if report.ok else "FAILED"
        detail = f"{report.rows} rows"
        if report.errors:
            detail = "; ".join(report.errors)
        print(f"  {name:<12} {status:>6}  {detail}")
    if args.repair_gaps:
        summaries = lake.repair_gaps(settings.symbol, settings.timeframe, mode=mode)
        repaired = {n: s for n, s in summaries.items() if s["gaps_found"]}
        print(f"gap repair: {len(repaired)} connector(s) had gaps" if repaired else "no gaps")
    failed = [n for n, r in reports.items() if not r.ok]
    print(f"ingested {len(reports) - len(failed)}/{len(reports)} connectors for {settings.symbol}")
    return 1 if failed else 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    lake = _build_lake(args)
    _print_json("data catalog", lake.catalog().datasets())
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    lake = _build_lake(args)
    _print_json("lake health", lake.health())
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
        "ingest": _cmd_ingest,
        "catalog": _cmd_catalog,
        "health": _cmd_health,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
