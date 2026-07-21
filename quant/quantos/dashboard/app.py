"""The Streamlit dashboard — a thin renderer over :mod:`quantos.dashboard.panels`.

Streamlit is an optional ``[dashboard]`` extra and is imported lazily inside
:func:`main`, so this module always imports offline (I6) and every number it
draws is computed (and tested) UI-free in the panels module. Run it with::

    streamlit run quantos/dashboard/app.py -- --lake-root .quantos-lake

Chart discipline (dataviz): stat tiles for headline metrics; equity and
drawdown as two separate single-series, single-axis charts (never a dual
axis); tables for positions, news, lab rankings and reliability bins —
identity lives in labels, not in invented palettes.
"""

from __future__ import annotations

from typing import Any

from quantos.dashboard.panels import build_dashboard_data
from quantos.data.store import DuckDBStore
from quantos.memory.archive import DecisionArchive

__all__ = ["main"]


def _require_streamlit() -> Any:
    try:
        import streamlit
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise ImportError(
            "the dashboard needs Streamlit — install the '[dashboard]' extra "
            "(pip install -e '.[dashboard]')"
        ) from exc
    return streamlit


def main(lake_root: str = ".quantos-lake") -> None:  # pragma: no cover - UI shell
    """Render the dashboard (requires the ``[dashboard]`` extra)."""
    st = _require_streamlit()
    store = DuckDBStore(root=lake_root)
    data = build_dashboard_data(store, DecisionArchive(store))

    st.title("quantos — research dashboard (paper only)")

    if "metrics" in data:
        metrics = data["metrics"]
        tiles = st.columns(4)
        tiles[0].metric("Sharpe", f"{metrics['sharpe']:.2f}")
        tiles[1].metric("Win rate", f"{metrics['win_rate']:.0%}")
        tiles[2].metric("Profit factor", f"{metrics['profit_factor']:.2f}")
        tiles[3].metric("Total return", f"{metrics['total_return']:.1%}")

    if "equity" in data:
        st.subheader("Equity")
        st.line_chart(data["equity"]["equity"])  # single series, single axis
        st.subheader("Drawdown")
        st.line_chart(data["equity"]["drawdown"])  # its own chart, never a dual axis

    if "decision" in data:
        st.subheader("AI thinking — latest decision")
        st.text(data["decision"]["narrative"])

    if "positions" in data:
        st.subheader("Open paper positions")
        st.table(data["positions"]["open_positions"])

    st.subheader("Decisions by regime")
    st.table(data["regimes"]["rows"])

    if data["news"]["rows"]:
        st.subheader("Latest news")
        st.table(data["news"]["rows"])

    if data["lab"]["rows"]:
        st.subheader("Strategy Lab — top ranked")
        st.table(data["lab"]["rows"])

    if "reliability" in data and data["reliability"]["fitted"]:
        st.subheader("Confidence reliability (stated vs realised)")
        st.table(data["reliability"]["bins"])


if __name__ == "__main__":  # pragma: no cover
    main()
