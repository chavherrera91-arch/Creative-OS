"""quantos quickstart — one command, end to end (offline, paper-only).

Run it from the ``quant/`` directory::

    python examples/quickstart.py
    python examples/quickstart.py --scenario COVID_CRASH --seed 3

It walks the whole research loop with deterministic synthetic data (no keys,
no network, I6): (1) it asks the Investment Committee for a decision and prints
the full explanation, (2) it backtests a strategy against the mandatory
baselines, and (3) it replays the scenario bar-by-bar through the paper broker.
Nothing here can touch real capital (I1); the same ``--seed`` always reproduces
the same run (I8).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run straight from a checkout without installing: put ``quant/`` on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantos.backtest.engine import backtest
from quantos.backtest.validation import deflated_sharpe_from_returns
from quantos.committee.committee import default_committee
from quantos.data.models import MarketSnapshot
from quantos.explain.explainer import explain_decision
from quantos.scenarios.library import get_scenario, scenario_names
from quantos.sim import MarketSimulator
from quantos.strategy.base import IndicatorStrategy
from quantos.strategy.generator import RandomStrategyGenerator


def rule(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="quantos end-to-end quickstart (paper only).")
    parser.add_argument(
        "--scenario", default="ETF_RALLY", choices=scenario_names(), help="market scenario to run"
    )
    parser.add_argument("--symbol", default="BTC/USDT", help="symbol label")
    parser.add_argument("--seed", type=int, default=7, help="random seed (reproducible, I8)")
    args = parser.parse_args()

    # -- data: a deterministic synthetic path (no network, I6) --------------
    scenario = get_scenario(args.scenario)
    ohlcv = scenario.generate(args.seed)
    print(f"Escenario: {scenario.name} — {scenario.description}")
    print(f"Datos: {len(ohlcv)} barras de {args.symbol} (sintéticas, semilla {args.seed})")

    # -- 1) a committee decision, fully explained (I4) ----------------------
    rule("1) DECISIÓN DEL COMITÉ DE INVERSIÓN")
    snapshot = MarketSnapshot(
        args.symbol,
        "1h",
        ohlcv.iloc[:200],
        macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
        sentiment={"score": 0.6},
        onchain={"whale_accumulation": 0.8},
    )
    decision = default_committee().deliberate(snapshot)
    print(explain_decision(decision))

    # -- 2) a backtest against the mandatory baselines (I9) -----------------
    rule("2) BACKTEST vs BASELINES (hay que ganarle a ambos para tener ventaja)")
    n_trials = 12
    specs = RandomStrategyGenerator().generate(n_trials, seed=args.seed, diversity=0.3)
    strategy = max(
        (IndicatorStrategy(s) for s in specs),
        key=lambda st: float(st.signals(ohlcv).diff().abs().sum()),
    )
    positions = strategy.signals(ohlcv)
    result = backtest(ohlcv, positions, fee_bps=10.0, slippage_bps=5.0)
    m = result.metrics
    print(f"Estrategia elegida : {strategy.spec.name} (familia {strategy.spec.family})")
    print(f"Retorno total      : {m['total_return'] * 100:+.2f}%")
    print(f"Sharpe (anualizado): {m['sharpe']:.2f}   <- se ve enorme, pero ojo (ver abajo)")
    print(f"Win rate           : {m['win_rate'] * 100:.1f}%   ({result.n_trades} operaciones)")
    print(f"Profit factor      : {m['profit_factor']:.2f}")
    print(f"¿Le gana al azar?         {'SÍ' if result.baselines.get('beats_random') else 'NO'}")
    print(
        f"¿Le gana a comprar&mantener? "
        f"{'SÍ' if result.baselines.get('beats_buy_and_hold') else 'NO'}"
    )

    # -- 2b) the honesty layer: don't get fooled by a big Sharpe (I9) -------
    honest = deflated_sharpe_from_returns(result.returns, n_trials=n_trials)
    print("\n  PRUEBA DE REALIDAD (esto es lo que de verdad importa):")
    print(f"  Probé {n_trials} estrategias y me quedé con la mejor. Ajustando por eso,")
    print(
        f"  el Sharpe deflactado = {honest['deflated_sharpe']:.0%} "
        "= probabilidad de que la ventaja sea real y no suerte."
    )
    print("  (El Sharpe anualizado infla el número; con datos sintéticos tan limpios,")
    print("   siempre se ve optimista. El número honesto es este, no el de arriba.)")

    # -- 3) real-time replay through the paper broker (I1/I2) ---------------
    rule("3) REPLAY EN TIEMPO REAL (barra por barra → broker de PAPEL)")
    replay = MarketSimulator(warmup=60, step=30).replay(scenario, seed=args.seed)
    print(f"Pasos simulados    : {len(replay.steps)}")
    print(f"Operaciones (papel): {replay.n_trades}")
    paper = replay.account["is_paper"]
    print(f"Equity final       : {replay.final_equity:,.0f}  (is_paper={paper})")
    print("Primeros pasos:")
    for step in replay.steps[:4]:
        print(
            f"  barra {step.index:>3}: {step.direction:<5} "
            f"aprobado={str(step.approved):<5} régimen={step.regime_label or '—'}"
        )

    rule("LISTO")
    print("Todo fue en papel, sin capital real (I1), sin mirar al futuro (I2),")
    print(f"y 100% reproducible: vuelve a correrlo con --seed {args.seed} y sale idéntico (I8).")


if __name__ == "__main__":
    main()
