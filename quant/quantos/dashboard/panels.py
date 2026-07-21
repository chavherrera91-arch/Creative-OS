"""Dashboard panels — pure data, no UI dependency (I6).

Each panel is a function from platform objects (``Store``, ``DecisionArchive``,
``BacktestResult``, ``PaperBroker``, ``ConfidenceCalibrator``) to a plain,
JSON-friendly dict the renderer draws. Keeping panels UI-free means they are
offline-testable and any front end (Streamlit today, Grafana/Hermes tomorrow)
consumes the same numbers.

Chart-design constraints follow the dataviz method: every time series ships as
a single-series, single-axis frame (equity and drawdown are separate panels,
never a dual axis), headline numbers are stat tiles, and identity is carried
by labels — not by colors the renderer would have to invent.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantos.backtest.engine import BacktestResult
from quantos.committee.calibration import ConfidenceCalibrator
from quantos.committee.decision import CommitteeDecision
from quantos.data.store import Store
from quantos.explain.explainer import explain_decision
from quantos.memory.archive import DecisionArchive
from quantos.paper.broker import PaperBroker

__all__ = [
    "build_dashboard_data",
    "decision_panel",
    "equity_panel",
    "lab_panel",
    "metrics_panel",
    "news_panel",
    "positions_panel",
    "regime_history_panel",
    "reliability_panel",
]


def equity_panel(result: BacktestResult) -> dict[str, Any]:
    """Equity curve + drawdown as two single-series frames (never one dual axis)."""
    equity = result.equity
    drawdown = equity / equity.cummax() - 1.0
    return {
        "equity": pd.DataFrame({"equity": equity}),
        "drawdown": pd.DataFrame({"drawdown": drawdown}),
        "final_equity": float(equity.iloc[-1]),
        "max_drawdown": float(drawdown.min()),
    }


def metrics_panel(result: BacktestResult) -> dict[str, Any]:
    """The headline stat tiles: Sharpe, win rate, profit factor, baselines."""
    metrics = result.metrics
    return {
        "sharpe": float(metrics.get("sharpe", 0.0)),
        "win_rate": float(metrics.get("win_rate", 0.0)),
        "profit_factor": float(metrics.get("profit_factor", 0.0)),
        "total_return": float(metrics.get("total_return", 0.0)),
        "n_trades": int(result.n_trades),
        "beats_buy_and_hold": bool(result.baselines.get("beats_buy_and_hold", False)),
        "beats_random": bool(result.baselines.get("beats_random", False)),
    }


def positions_panel(broker: PaperBroker) -> dict[str, Any]:
    """Open paper positions and account state (paper only, I1)."""
    symbols = sorted({trade.symbol for trade in broker.trades})
    open_positions = [
        {"symbol": symbol, "position": broker.position(symbol)}
        for symbol in symbols
        if abs(broker.position(symbol)) > 1e-12
    ]
    return {
        "cash": float(broker.cash),
        "equity": float(broker.equity()),
        "n_trades": len(broker.trades),
        "open_positions": open_positions,
    }


def decision_panel(decision: CommitteeDecision) -> dict[str, Any]:
    """'AI thinking': the latest decision's headline + full narrative."""
    return {
        "symbol": decision.symbol,
        "direction": decision.direction.value,
        "approved": decision.approved,
        "confidence": decision.confidence,
        "regime": decision.regime.get("label", ""),
        "blocked_by_risk": decision.blocked_by_risk,
        "narrative": explain_decision(decision),
    }


def regime_history_panel(archive: DecisionArchive) -> dict[str, Any]:
    """Decision counts and mean outcome per regime — heatmap-ready rows."""
    rows: dict[str, dict[str, float]] = {}
    for record in archive.query():
        label = record.regime_label or "unknown"
        cell = rows.setdefault(label, {"n": 0.0, "closed": 0.0, "pnl_sum": 0.0})
        cell["n"] += 1
        if record.closed and record.pnl is not None:
            cell["closed"] += 1
            cell["pnl_sum"] += record.pnl
    table = [
        {
            "regime": label,
            "decisions": cell["n"],
            "closed": cell["closed"],
            "mean_pnl": cell["pnl_sum"] / cell["closed"] if cell["closed"] else 0.0,
        }
        for label, cell in sorted(rows.items())
    ]
    return {"rows": table}


def reliability_panel(calibrator: ConfidenceCalibrator) -> dict[str, Any]:
    """Stated-vs-realised confidence bins (WP-7.6's dashboard hook)."""
    return {"bins": calibrator.reliability(), "fitted": calibrator.fitted}


def news_panel(store: Store, limit: int = 20) -> dict[str, Any]:
    """Latest curated headlines from the lake's news connector."""
    frame = store.read("curated", "news")
    if frame.empty:
        return {"rows": []}
    frame = frame.sort_values("event_time", ascending=False).head(limit)
    columns = [c for c in ("event_time", "headline", "tag", "sentiment") if c in frame.columns]
    rows = frame[columns].copy()
    if "event_time" in rows.columns:
        rows["event_time"] = rows["event_time"].astype(str)
    return {"rows": rows.to_dict(orient="records")}


def lab_panel(store: Store, limit: int = 10) -> dict[str, Any]:
    """Top Strategy Lab results persisted by M5 (fitness-ranked)."""
    frame = store.read("features", "strategy_lab")
    if frame.empty:
        return {"rows": []}
    columns = [
        c
        for c in ("rank", "family", "tested_regime", "fitness", "deflated_sharpe", "survived")
        if c in frame.columns
    ]
    top = frame.sort_values("fitness", ascending=False).head(limit)
    return {"rows": top[columns].to_dict(orient="records")}


def build_dashboard_data(
    store: Store,
    archive: DecisionArchive,
    *,
    backtest: BacktestResult | None = None,
    broker: PaperBroker | None = None,
    decision: CommitteeDecision | None = None,
    calibrator: ConfidenceCalibrator | None = None,
) -> dict[str, Any]:
    """Assemble every panel the renderer needs, in one offline pass."""
    data: dict[str, Any] = {
        "regimes": regime_history_panel(archive),
        "news": news_panel(store),
        "lab": lab_panel(store),
    }
    if backtest is not None:
        data["equity"] = equity_panel(backtest)
        data["metrics"] = metrics_panel(backtest)
    if broker is not None:
        data["positions"] = positions_panel(broker)
    if decision is not None:
        data["decision"] = decision_panel(decision)
    if calibrator is not None:
        data["reliability"] = reliability_panel(calibrator)
    return data
