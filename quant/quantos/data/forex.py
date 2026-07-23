"""Forex market data — real rates from Yahoo Finance, synthetic fallback.

The whole platform (strategies, committee, scorecard, miner) is market-agnostic
— it only needs an OHLCV frame. Crypto comes from ccxt; this adds **Forex**
(``EUR/USD``, ``GBP/USD``, ...) from Yahoo Finance via the optional
``yfinance`` package (free, no API key, read-only). When yfinance or the
network is unavailable it falls back to the deterministic synthetic generator
and labels the source honestly (I3/I6) — it never passes fake data off as real.
"""

from __future__ import annotations

import pandas as pd

from quantos.data.collector import synthetic_ohlcv

__all__ = ["fetch_forex_ohlcv", "to_yahoo_symbol"]

#: Yahoo intraday intervals; longer timeframes fall back to daily bars.
_YAHOO_INTERVAL = {"1h": "1h", "60m": "1h", "1d": "1d", "1wk": "1wk"}


def to_yahoo_symbol(symbol: str) -> str:
    """``EUR/USD`` → ``EURUSD=X`` (Yahoo's forex ticker form)."""
    return symbol.replace("/", "").replace(" ", "").upper() + "=X"


def fetch_forex_ohlcv(
    symbol: str = "EUR/USD",
    timeframe: str = "1h",
    bars: int = 400,
    force_synthetic: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch Forex OHLCV; returns ``(frame, source)`` (``"yfinance"``/``"synthetic"``).

    Real data needs the ``yfinance`` package and a working network; any failure
    degrades to synthetic and says so in ``source`` — never a fake "real" label.
    """
    if not force_synthetic:
        frame = _from_yahoo(symbol, timeframe, bars)
        if frame is not None:
            return frame, "yfinance"
    # Forex prices live near ~1.0, so a small start price keeps the synthetic
    # candles realistic-looking (unlike crypto's 50k).
    synthetic = synthetic_ohlcv(symbol, timeframe=timeframe, bars=bars, start_price=1.10)
    return synthetic, "synthetic"


def _from_yahoo(symbol: str, timeframe: str, bars: int) -> pd.DataFrame | None:
    """Best-effort real fetch; None on any missing dependency / network issue."""
    try:
        import yfinance as yf

        interval = _YAHOO_INTERVAL.get(timeframe, "1h")
        period = "60d" if interval == "1h" else "2y"
        raw = yf.download(
            to_yahoo_symbol(symbol),
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
        )
        if raw is None or len(raw) < 60:
            return None
        # yfinance may return MultiIndex columns for a single ticker.
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns=str.lower)
        frame = raw[["open", "high", "low", "close", "volume"]].tail(bars).astype(float)
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame.index.name = None
        # Forex volume on Yahoo is often 0; give the cost model a nominal figure.
        if float(frame["volume"].abs().sum()) == 0.0:
            frame["volume"] = 1_000_000.0
        return frame
    except Exception:  # noqa: BLE001 - any failure falls back to synthetic (I3/I6)
        return None
