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

from quantos.dashboard.demo import build_live_data, load_lab_ohlcv, run_strategy_lab
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

    _strategy_lab_section(st, scenario, seed)
    _vault_section(st)
    _live_paper_section(st)


def _vault_section(st: Any) -> None:  # pragma: no cover - UI
    """Show the gold the automatic miner has saved to the vault."""
    import pandas as pd

    from quantos.mining import StrategyVault

    st.divider()
    st.subheader("🏆 Bóveda de oro — estrategias que el minero guardó")
    st.caption(
        "El minero cava solo (aunque no estés) y **guarda aquí** las estrategias que "
        "pasan el examen honesto. Enciéndelo con el ícono **Minar quantos**."
    )
    vault = StrategyVault()
    gold = vault.top(50)
    if not gold:
        st.info(
            "La bóveda está vacía todavía. Abre el ícono **Minar quantos** de tu escritorio "
            "y déjalo corriendo — cada tanto cava y va guardando el oro aquí."
        )
        return
    rows = [
        {
            "familia": g.family,
            "confianza_real": g.deflated_sharpe,
            "sharpe_fuera_muestra": g.oos_sharpe,
            "régimen": g.regime,
            "datos": g.source,
            "estrategia": g.name,
        }
        for g in gold
    ]
    st.caption(f"**{len(gold)}** estrategias de oro guardadas (mejor primero).")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _live_paper_section(st: Any) -> None:  # pragma: no cover - UI
    """A demo account: real live prices, real-time decisions, fake money (I1)."""
    import pandas as pd

    from quantos.live import LivePaperTrader

    st.divider()
    st.subheader("📡 Demo en vivo — paper trading")
    st.caption(
        "Precios **reales** del mercado y decisiones en **tiempo real**, pero con dinero "
        "**ficticio** — como una cuenta demo. Nunca se mueve capital real (I1)."
    )

    cols = st.columns([2, 1, 1])
    symbol = cols[0].text_input("Símbolo", value="BTC/USDT", key="live_symbol")
    do_step = cols[1].button("▶ Dar un paso", type="primary")
    do_reset = cols[2].button("↺ Reiniciar")

    trader = LivePaperTrader(symbol=symbol)
    if do_reset:
        trader.reset()
        st.success("Cuenta demo reiniciada a la plata inicial.")
    if do_step:
        with st.spinner("Trayendo el precio real y consultando al comité…"):
            try:
                step = trader.step()
                real = step["source"] == "ccxt"
                src = "precio REAL ✅" if real else "precio simulado (sin conexión) ⚠️"
                verdict = "aprobada" if step["approved"] else "stand-down"
                acted = "operó" if step["traded"] else "sin operar"
                st.success(
                    f"{src} · {step['price']:,.2f} · decisión **{step['direction']}** "
                    f"({verdict}) · {acted}"
                )
            except Exception as exc:  # noqa: BLE001 - surface any live-data hiccup
                st.error(f"No se pudo dar el paso (¿sin internet?): {exc}")

    account = trader.account()
    history = account["history"]
    equity_now = float(history[-1]["equity"]) if history else trader.cash
    pnl = equity_now - trader.cash
    tiles = st.columns(3)
    tiles[0].metric("Equity (papel)", f"${equity_now:,.0f}", f"{pnl:+,.0f}")
    tiles[1].metric("Operaciones", account["n_trades"])
    tiles[2].metric("Pasos dados", len(history))

    if history:
        frame = pd.DataFrame(history)
        st.line_chart(frame.set_index("as_of")["equity"])
        st.dataframe(frame.tail(12), width="stretch", hide_index=True)
    else:
        st.info(
            "Aún no hay pasos. Dale a **▶ Dar un paso**: trae el precio real de ahora, el "
            "comité decide, y se ejecuta con dinero ficticio. Cada clic = un momento en vivo."
        )


def _strategy_lab_section(st: Any, scenario: str, seed: int) -> None:  # pragma: no cover - UI
    """Generate many strategies, test them, keep the profitable ones, drop the rest."""
    import pandas as pd

    st.divider()
    st.subheader("🧪 Laboratorio de Estrategias")
    st.caption(
        "Genera muchas estrategias, las prueba con un examen honesto, **guarda** las "
        "rentables y **descarta** el resto."
    )
    col_a, col_b = st.columns([1, 1])
    source_label = col_a.radio("Datos", ["Demo (simulado)", "Exchange real"], horizontal=True)
    symbol = col_b.text_input("Símbolo (para exchange real)", value="BTC/USDT")

    if not st.button("Buscar estrategias rentables", type="primary"):
        return
    source = "real" if source_label.startswith("Exchange") else "demo"
    with st.spinner("Probando 30 estrategias… (unos segundos)"):
        ohlcv, data_label = load_lab_ohlcv(source, scenario, symbol, seed)
        lab = run_strategy_lab(ohlcv, symbol, seed)

    st.caption(
        f"Datos: **{data_label}** · régimen **{lab['regimen']}** · "
        f"probadas **{lab['probadas']}** → guardadas **{lab['guardadas']}** · "
        f"riesgo de sobreajuste (PBO) {lab['pbo']:.0%}"
    )
    frame = pd.DataFrame(lab["rows"])
    st.dataframe(frame, width="stretch", hide_index=True)
    st.info(
        "En datos **simulados** los números salen exagerados (el mercado de ejemplo es "
        "demasiado limpio). Lo que de verdad importa es **confianza_real** — la probabilidad "
        "de que la ventaja no sea suerte. Con **Exchange real** los números son realistas."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
