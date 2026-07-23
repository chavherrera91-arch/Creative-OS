"""Build a full, live dashboard payload from a seeded synthetic run (UI-free).

The Streamlit app calls :func:`build_live_data` so it *works the moment you
open it* — no lake to populate first. Everything here is core (numpy/pandas/
duckdb), deterministic and offline (I6/I8): a committee decision, a backtest
with the statistical-honesty layer (Deflated Sharpe, I9), a regime archive and
a confidence-calibration map. It is pure data, so it is unit-tested without
Streamlit.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantos.backtest.engine import backtest
from quantos.backtest.validation import deflated_sharpe_from_returns
from quantos.committee.calibration import ConfidenceCalibrator
from quantos.committee.committee import default_committee
from quantos.dashboard.panels import (
    decision_panel,
    equity_panel,
    metrics_panel,
    regime_history_panel,
)
from quantos.data.models import MarketSnapshot
from quantos.memory import DecisionArchive
from quantos.regime.classifier import RuleRegimeClassifier
from quantos.scenarios.library import get_scenario
from quantos.strategy.base import IndicatorStrategy
from quantos.strategy.generator import RandomStrategyGenerator
from quantos.strategy.lab import StrategyLab

__all__ = ["build_live_data", "load_lab_ohlcv", "run_strategy_lab"]


def _full_snapshot(symbol: str, ohlcv: pd.DataFrame) -> MarketSnapshot:
    """A snapshot with every channel so the full five-analyst panel votes."""
    return MarketSnapshot(
        symbol,
        "1h",
        ohlcv,
        macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
        sentiment={"score": 0.6},
        onchain={"whale_accumulation": 0.8},
    )


def build_live_data(
    scenario: str = "ETF_RALLY", seed: int = 7, n_trials: int = 12, symbol: str = "BTC/USDT"
) -> dict[str, Any]:
    """Run a seeded scenario end to end and return every panel's data (I8)."""
    scn = get_scenario(scenario)
    ohlcv = scn.generate(seed)

    # -- committee decision (full panel) ------------------------------------
    decision = default_committee().deliberate(_full_snapshot(symbol, ohlcv.iloc[:200]))
    dec = decision_panel(decision)
    dec["regime"] = RuleRegimeClassifier().classify(_full_snapshot(symbol, ohlcv.iloc[:200])).label

    # -- backtest + honesty layer (best of N trials) ------------------------
    specs = RandomStrategyGenerator().generate(n_trials, seed=seed, diversity=0.3)
    strategy = max(
        (IndicatorStrategy(s) for s in specs),
        key=lambda st: float(st.signals(ohlcv).diff().abs().sum()),
    )
    result = backtest(ohlcv, strategy.signals(ohlcv), fee_bps=10.0, slippage_bps=5.0)
    equity = equity_panel(result)
    metrics = metrics_panel(result)
    dsr = deflated_sharpe_from_returns(result.returns, n_trials=n_trials)
    metrics["deflated_sharpe"] = round(dsr["deflated_sharpe"], 4)
    metrics["n_trials"] = n_trials

    # -- regime archive (a walk of decisions with realised outcomes) --------
    classifier = RuleRegimeClassifier()
    archive = DecisionArchive()
    rng = np.random.default_rng(seed + 1)
    for i in range(36):
        end = 60 + i * 6
        window = ohlcv.iloc[:end]
        snap = MarketSnapshot(symbol, "1h", window)
        rec = default_committee().deliberate(snap).as_dict()
        rec["regime"] = classifier.classify(snap).as_dict()
        rec["as_of"] = str(window.index[-1])
        rec["reasons"] = [f"walk-{i}"]
        did = archive.record(rec)
        fwd = float(
            ohlcv["close"].iloc[min(end + 6, len(ohlcv) - 1)] / ohlcv["close"].iloc[end - 1] - 1.0
        )
        s = {"LONG": 1.0, "SHORT": -1.0}.get(rec.get("direction", "FLAT"), 0.0)
        archive.record_outcome(did, pnl=round(s * fwd * 1000 + rng.normal(0, 3), 2))
    calibrator = ConfidenceCalibrator().fit(archive)

    return {
        "scenario": scn.name,
        "description": scn.description,
        "symbol": symbol,
        "n_bars": int(len(ohlcv)),
        "seed": seed,
        "equity": equity,
        "metrics": metrics,
        "decision": dec,
        "regimes": regime_history_panel(archive)["rows"],
        "reliability": {"bins": calibrator.reliability(), "fitted": calibrator.fitted},
        "strategy": {"name": strategy.spec.name, "family": strategy.spec.family},
    }


def load_lab_ohlcv(
    source: str, scenario: str, symbol: str, seed: int = 7, bars: int = 400
) -> tuple[pd.DataFrame, str]:
    """Load bars for the lab: a synthetic scenario, or real exchange data.

    ``source="real"`` fetches through the read-only :class:`DataCollector`
    (ccxt); if ccxt/network are unavailable it falls back to synthetic and
    says so in the returned label — it never fabricates a "real" source (I3).
    """
    if source == "real":
        from quantos.config import Settings
        from quantos.data.collector import DataCollector

        base = Settings.from_env()
        settings = Settings(
            **{**base.as_dict(), "symbol": symbol, "bars": bars, "seed": seed}  # type: ignore[arg-type]
        )
        collector = DataCollector(settings=settings, force_synthetic=False)
        return collector.fetch_ohlcv(), f"{symbol} — fuente: {collector.last_source}"
    scn = get_scenario(scenario)
    return scn.generate(seed), f"{scn.name} (demo simulado)"


def _verdict(survived: bool, oos_sharpe: float, dsr: float, min_dsr: float) -> str:
    """Plain-language reason a candidate was kept or discarded."""
    if survived:
        return "Guardada — rentable y validada"
    if oos_sharpe <= 0:
        return "Descartada — perdió fuera de muestra"
    if dsr < min_dsr:
        return "Descartada — la ventaja pudo ser suerte"
    return "Descartada — otras fueron mejores"


def run_strategy_lab(
    ohlcv: pd.DataFrame,
    symbol: str = "BTC/USDT",
    seed: int = 7,
    n_candidates: int = 30,
    top_k: int = 8,
    min_dsr: float = 0.5,
) -> dict[str, Any]:
    """Generate many strategies, test them honestly, keep the good, drop the rest.

    Returns a table where each row says whether the strategy was *saved*
    (profitable out-of-sample and past the honesty gate) or *discarded*, with
    a plain reason — the research funnel made visible (I9). Deterministic (I8).
    """
    specs = RandomStrategyGenerator().generate(n_candidates, seed=seed, diversity=0.5)
    result = StrategyLab(top_k=top_k, min_dsr=min_dsr, symbol=symbol).run(specs, ohlcv)
    rows = []
    for record in result.records:
        oos = float(record.oos_metrics.get("sharpe", 0.0))
        dsr = float(record.validation.get("deflated_sharpe", 0.0))
        rows.append(
            {
                "guardada": record.survived,
                "familia": record.spec.family,
                "estrategia": record.spec.name,
                "sharpe_fuera_muestra": round(oos, 2),
                "confianza_real": round(dsr, 4),
                "operaciones": record.n_trades,
                "veredicto": _verdict(record.survived, oos, dsr, min_dsr),
            }
        )
    return {
        "probadas": len(specs),
        "guardadas": len(result.survivors),
        "pbo": result.pbo,
        "regimen": result.tested_regime,
        "rows": rows,
    }
