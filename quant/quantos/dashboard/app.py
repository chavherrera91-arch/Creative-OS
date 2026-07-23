"""The Streamlit dashboard — a working app over :mod:`quantos.dashboard`.

Streamlit is an optional ``[dashboard]`` extra and is imported lazily inside
:func:`main`, so this module always imports offline (I6). Every number it draws
is computed (and tested) UI-free in :mod:`quantos.dashboard.demo` /
:mod:`quantos.dashboard.panels`. Launch it with one command::

    quantos-app            # after: pip install -e '.[dashboard]'
    # or:  streamlit run quantos/dashboard/app.py

It opens in the browser and runs a full seeded research pass out of the box
(no lake to populate first): a committee decision, a backtest with the
Deflated-Sharpe honesty layer (I9), regime history and confidence calibration.

Chart discipline (dataviz): stat tiles for headlines; equity and drawdown as
two separate single-series, single-axis charts (never a dual axis); tables for
the rest — identity lives in labels, not invented palettes.
"""

from __future__ import annotations

from typing import Any

from quantos.dashboard.demo import build_live_data
from quantos.scenarios.library import scenario_names

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


def main() -> None:  # pragma: no cover - UI shell
    """Render the interactive dashboard (requires the ``[dashboard]`` extra)."""
    st = _require_streamlit()
    st.set_page_config(page_title="quantos — research terminal", page_icon="📈", layout="wide")

    st.sidebar.title("quantos")
    st.sidebar.caption("AI Quant Research Platform")
    st.sidebar.warning("RESEARCH MODE — no live capital (I1)")
    scenario = st.sidebar.selectbox("Scenario", scenario_names(), index=0)
    seed = int(st.sidebar.number_input("Seed", min_value=0, max_value=9999, value=7, step=1))
    st.sidebar.button("Run", type="primary")  # any rerun rebuilds with the inputs

    # Cache the (heavy) research pass so re-runs are instant, and show progress
    # on the first cold run — otherwise the silent launch looks like a hang.
    loader = st.cache_data(show_spinner=False)(build_live_data)
    with st.spinner("Corriendo el análisis del comité… (unos segundos la primera vez)"):
        data = loader(scenario, seed)

    st.title("quantos — research terminal")
    st.caption(
        f"{data['scenario']} · {data['symbol']} · {data['n_bars']} bars · "
        f"strategy {data['strategy']['name']} · seeded & deterministic"
    )

    # -- headline metrics + the honesty layer (I9) --------------------------
    m = data["metrics"]
    tiles = st.columns(5)
    tiles[0].metric("Total return", f"{m['total_return']:+.1%}")
    tiles[1].metric("Sharpe (annualised)", f"{m['sharpe']:.2f}")
    tiles[2].metric("Win rate", f"{m['win_rate']:.0%}", f"{m['n_trades']} trades")
    tiles[3].metric("Profit factor", f"{m['profit_factor']:.2f}")
    tiles[4].metric("Deflated Sharpe", f"{m['deflated_sharpe']:.0%}", "prob. edge is real")
    st.info(
        f"Reality check (I9): that Sharpe of {m['sharpe']:.1f} is annualised on clean "
        f"synthetic data — flattering. This run picked the best of {m['n_trials']} strategies, so "
        f"the honest figure is the **Deflated Sharpe = {m['deflated_sharpe']:.0%}** (probability "
        f"the edge is real once selection is accounted for). Beats buy & hold: "
        f"{'yes' if m['beats_buy_and_hold'] else 'no'} · beats random: "
        f"{'yes' if m['beats_random'] else 'no'}."
    )

    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("Equity curve")
        st.line_chart(data["equity"]["equity"])  # single series, single axis
        st.subheader("Drawdown")
        st.line_chart(data["equity"]["drawdown"])  # its own chart, never a dual axis
    with right:
        st.subheader("Investment Committee")
        dec = data["decision"]
        verdict = f"{dec['direction']} — {'APPROVED' if dec['approved'] else 'STAND DOWN'}"
        (st.success if dec["approved"] else st.warning)(f"{verdict}  ·  regime {dec['regime']}")
        st.caption(f"Composite confidence {dec['confidence']:.0%}")
        st.text(dec["narrative"])

    st.subheader("Decisions by regime")
    st.table(data["regimes"])

    st.subheader("Confidence calibration")
    if data["reliability"]["fitted"]:
        st.table(data["reliability"]["bins"])
    else:
        st.caption(
            "Cold-start: the calibration map is the identity diagonal — the platform "
            "will not claim calibration it hasn't earned yet (I3/I9). Points appear once "
            "enough decisions close."
        )


if __name__ == "__main__":  # pragma: no cover
    main()
