"""Read-only market data collection.

Uses ``ccxt`` for real public OHLCV when available, and otherwise falls back to a
deterministic synthetic generator so the whole platform runs offline with no
keys. This module never sends orders — it only reads public market data.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from quantos.data.models import MarketSnapshot

# Bar length in minutes for the synthetic clock.
_TF_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
}


def _ccxt_available() -> bool:
    try:
        import ccxt  # noqa: F401
    except Exception:
        return False
    return True


def _seed_from_symbol(symbol: str) -> int:
    digest = hashlib.sha256(symbol.encode()).hexdigest()
    return int(digest[:8], 16)


def synthetic_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 500,
    *,
    seed: int | None = None,
    trend: float = 0.0,
    volatility: float = 0.02,
    start_price: float = 100.0,
) -> pd.DataFrame:
    """Deterministic GBM-style OHLCV for offline research and tests.

    ``trend`` is a per-bar drift; positive => generally rising series. The seed
    is derived from the symbol unless overridden, so a given symbol always
    yields the same series (reproducible research).
    """
    if seed is None:
        seed = _seed_from_symbol(symbol)
    rng = np.random.default_rng(seed)

    minutes = _TF_MINUTES.get(timeframe, 60)
    shocks = rng.normal(loc=trend, scale=volatility, size=limit)
    close = start_price * np.exp(np.cumsum(shocks))

    # Build plausible OHLC around each close.
    prev_close = np.concatenate([[start_price], close[:-1]])
    open_ = prev_close
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, volatility / 2, limit)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, volatility / 2, limit)))
    volume = rng.lognormal(mean=10, sigma=0.5, size=limit)

    end = pd.Timestamp.now("UTC").floor("min")
    index = pd.date_range(end=end, periods=limit, freq=f"{minutes}min", name="timestamp")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


class DataCollector:
    """Fetches read-only OHLCV, transparently falling back to synthetic data."""

    def __init__(self, source: str = "auto", exchange: str = "binance") -> None:
        self.source = source
        self.exchange = exchange
        self._client = None

    # -- public API -----------------------------------------------------------
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        **synthetic_kwargs,
    ) -> pd.DataFrame:
        use_ccxt = self.source == "ccxt" or (self.source == "auto" and _ccxt_available())
        if use_ccxt:
            try:
                return self._fetch_ccxt(symbol, timeframe, limit)
            except Exception:
                if self.source == "ccxt":
                    raise  # explicit ccxt request => surface the error
        return synthetic_ohlcv(symbol, timeframe, limit, **synthetic_kwargs)

    def snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        *,
        context: dict | None = None,
        **synthetic_kwargs,
    ) -> MarketSnapshot:
        """Assemble a :class:`MarketSnapshot`. ``context`` supplies optional
        derivatives / macro / sentiment / on-chain / events channels."""
        ohlcv = self.fetch_ohlcv(symbol, timeframe, limit, **synthetic_kwargs)
        context = context or {}
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv=ohlcv,
            derivatives=context.get("derivatives", {}),
            onchain=context.get("onchain", {}),
            macro=context.get("macro", {}),
            sentiment=context.get("sentiment", {}),
            events=context.get("events", {}),
            news=context.get("news", []),
        )

    # -- ccxt backend ---------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            import ccxt

            self._client = getattr(ccxt, self.exchange)({"enableRateLimit": True})
        return self._client

    def _fetch_ccxt(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        client = self._get_client()
        raw = client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.drop(columns="ts").set_index("timestamp")
