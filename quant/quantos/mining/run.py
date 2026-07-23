"""``quantos-miner`` — run the strategy miner unattended, digging on a schedule.

Starts an endless (or bounded) mining loop that saves gold to the vault while
you are away. Progress is written to a log file so a silently-launched miner
still leaves a trace. Paper research only — no capital is ever at risk (I1).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantos.mining.miner import StrategyMiner
from quantos.mining.vault import StrategyVault

__all__ = ["main"]


def log_path() -> Path:
    """Where the miner records its progress."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "quantos" / "miner.log"


def _parse_markets(spec: str) -> list[tuple[str, str]]:
    """Parse ``'BTC/USDT:crypto,EUR/USD:forex'`` → ``[(sym, kind), ...]``.

    A part without ``:kind`` defaults to crypto, unless it is a fiat pair.
    """
    fiat = {"USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD"}
    out: list[tuple[str, str]] = []
    for raw in spec.split(","):
        part = raw.strip()
        if not part:
            continue
        if ":" in part:
            sym, kind = part.split(":", 1)
        else:
            sym = part
            quote = part.split("/")[-1].upper() if "/" in part else ""
            kind = "forex" if quote in fiat and "USDT" not in part.upper() else "crypto"
        out.append((sym.strip(), kind.strip()))
    return out or [("BTC/USDT", "crypto")]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="quantos strategy miner (paper research).")
    parser.add_argument("--symbol", default="BTC/USDT", help="par a minar, ej. BTC/USDT o EUR/USD")
    parser.add_argument(
        "--market",
        default="crypto",
        choices=("crypto", "forex"),
        help="crypto (Binance/ccxt) o forex (Yahoo Finance)",
    )
    parser.add_argument(
        "--interval", type=float, default=1800.0, help="seconds between digs (default 30 min)"
    )
    parser.add_argument("--rounds", type=int, default=None, help="stop after N digs (else forever)")
    parser.add_argument("--min-dsr", type=float, default=0.6, help="honesty gate for gold (I9)")
    parser.add_argument(
        "--candidates",
        type=int,
        default=40,
        help="strategies tested per round (más = más exploración, mismo rigor)",
    )
    parser.add_argument(
        "--markets",
        default=None,
        help="varios mercados juntos, ej. 'BTC/USDT:crypto,ETH/USDT:crypto,EUR/USD:forex' "
        "(una que pase en 2+ es un diamante 💎)",
    )
    parser.add_argument(
        "--synthetic", action="store_true", help="mine synthetic scenarios (no network)"
    )
    args = parser.parse_args(argv)

    markets = _parse_markets(args.markets) if args.markets else [(args.symbol, args.market)]
    vault = StrategyVault()
    miner = StrategyMiner(
        vault=vault,
        symbol=args.symbol,
        min_dsr=args.min_dsr,
        n_candidates=max(2, args.candidates),
        force_synthetic=args.synthetic,
        market=args.market,
        markets=markets,
    )
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)

    def on_round(summary: dict[str, Any]) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if "error" in summary:
            line = f"[{stamp}] ronda {summary['round']} ERROR: {summary['error']}"
        else:
            diamonds = summary.get("diamonds", 0)
            gem = f", 💎 {diamonds}" if diamonds else ""
            line = (
                f"[{stamp}] ronda {summary['round']} · {summary.get('n_markets', 1)} mercado(s) · "
                f"{summary['source']} · probadas {summary['tested']} · "
                f"oro {summary['gold_found']} (nuevos {summary['new_in_vault']}{gem}) · "
                f"bóveda {summary['vault_size']}"
            )
        print(line, flush=True)
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    print(f"Minero quantos iniciado (bóveda: {vault.path}). Ctrl+C para detener.", flush=True)
    try:
        miner.run(rounds=args.rounds, interval_seconds=args.interval, on_round=on_round)
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        print("Minero detenido.", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
