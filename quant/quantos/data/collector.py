"""Read-only market data collection with a deterministic synthetic fallback.

The collector *never* places orders — it only reads candles (invariant I1).
When ``ccxt`` is unavailable (it is an optional extra), or the network fails,
or ``force_synthetic`` is set, a seeded synthetic generator produces a
reproducible OHLCV path so the whole platform runs offline (invariants I6, I8).
"""

from __future__ import annotations

import zlib
from typing import Any

import numpy as np
import pandas as pd

from quantos.config import Settings
from quantos.data.models import MarketSnapshot

__all__ = ["DataCollector", "synthetic_channels", "synthetic_ohlcv", "timeframe_to_freq"]

_SYNTHETIC_EPOCH = "2024-01-01"  # fixed anchor: no wall clock in research paths (I8)

_TIMEFRAME_FREQ: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


def timeframe_to_freq(timeframe: str) -> str:
    """Map an exchange timeframe (``"1h"``) to a pandas frequency string."""
    try:
        return _TIMEFRAME_FREQ[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe {timeframe!r}") from exc


def _mix_seed(symbol: str, timeframe: str, seed: int) -> int:
    """Derive a per-(symbol, timeframe) seed from the global seed (I8)."""
    return (zlib.crc32(f"{symbol}|{timeframe}".encode()) ^ seed) & 0xFFFFFFFF


def synthetic_ohlcv(
    symbol: str,
    timeframe: str,
    bars: int = 400,
    seed: int = 42,
    start_price: float = 50_000.0,
) -> pd.DataFrame:
    """Deterministic synthetic OHLCV frame.

    A regime-flavoured geometric random walk: drift and volatility shift a few
    times over the sample so trend/range/vol-spike behaviour all appear. The
    output is a pure function of the arguments — same inputs, same candles.

    Args:
        symbol: pair name; folded into the seed so different symbols differ.
        timeframe: bar timeframe (also folded into the seed).
        bars: number of bars.
        seed: global seed (I8).
        start_price: first open.

    Returns:
        DataFrame indexed by UTC timestamps with columns
        ``open, high, low, close, volume``.
    """
    if bars < 2:
        raise ValueError("bars must be >= 2")
    rng = np.random.default_rng(_mix_seed(symbol, timeframe, seed))

    n_segments = max(1, bars // 100)
    seg_len = int(np.ceil(bars / n_segments))
    drifts = rng.normal(0.0, 0.0012, size=n_segments)
    vols = rng.uniform(0.004, 0.014, size=n_segments)
    drift = np.repeat(drifts, seg_len)[:bars]
    vol = np.repeat(vols, seg_len)[:bars]

    log_ret = rng.normal(0.0, 1.0, size=bars) * vol + drift
    close = start_price * np.exp(np.cumsum(log_ret))
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.normal(0.0, 0.5, size=bars)) * vol * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    volume = rng.lognormal(mean=4.0, sigma=0.4, size=bars) * (1.0 + 20.0 * vol)

    index = pd.date_range(
        _SYNTHETIC_EPOCH, periods=bars, freq=timeframe_to_freq(timeframe), tz="UTC"
    )
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def synthetic_channels(symbol: str, seed: int = 42) -> dict[str, Any]:
    """Deterministic synthetic non-price channels for a full snapshot.

    Used by tests and demos that need macro/sentiment/on-chain data offline.
    Real channel ingestion is Milestone 2.
    """
    rng = np.random.default_rng(_mix_seed(symbol, "channels", seed))
    return {
        "derivatives": {
            "funding_rate": float(rng.normal(0.0, 0.0004)),
            "open_interest_change": float(rng.normal(0.0, 0.05)),
            "basis_bps": float(rng.normal(5.0, 10.0)),
            "long_short_ratio": float(rng.uniform(0.7, 1.4)),
        },
        "onchain": {
            "net_exchange_flow": float(rng.normal(0.0, 1_000.0)),
            "whale_accumulation": float(rng.normal(0.0, 0.5)),
            "stablecoin_supply_change": float(rng.normal(0.0, 0.02)),
        },
        "macro": {
            "dxy_trend": float(rng.normal(0.0, 0.5)),
            "rates_trend": float(rng.normal(0.0, 0.5)),
            "risk_appetite": float(rng.normal(0.0, 0.5)),
        },
        "sentiment": {
            "score": float(np.clip(rng.normal(0.0, 0.4), -1.0, 1.0)),
            "volume": float(rng.uniform(0.0, 1.0)),
        },
        "events": [],
        "news": [],
    }


class DataCollector:
    """Fetch market snapshots, read-only, with a guaranteed offline path.

    The collector exposes no order-placing capability of any kind (I1). ccxt is
    imported lazily and only used for public, unauthenticated candle reads; any
    failure (missing package, network, exchange error) falls back to the
    deterministic synthetic generator.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        force_synthetic: bool = False,
        exchange: Any | None = None,
    ) -> None:
        """
        Args:
            settings: platform settings (defaults used when omitted).
            force_synthetic: never touch the network, always synthesise.
            exchange: pre-built ccxt-like exchange (dependency injection for
                tests); must expose ``fetch_ohlcv``.
        """
        self.settings = settings or Settings()
        self.force_synthetic = force_synthetic
        self._exchange = exchange
        self.last_source: str = "none"

    def _build_exchange(self) -> Any | None:
        """Lazily build a read-only ccxt exchange; None when unavailable."""
        if self._exchange is not None:
            return self._exchange
        try:
            import ccxt  # noqa: PLC0415 — optional extra, lazy on purpose (I6)
        except ImportError:
            return None
        try:
            exchange_cls = getattr(ccxt, self.settings.exchange_id)
            self._exchange = exchange_cls({"enableRateLimit": True})
        except Exception:
            return None
        return self._exchange

    def fetch_ohlcv(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
        bars: int | None = None,
        seed: int | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV, falling back to deterministic synthetic data.

        Returns:
            OHLCV frame; ``self.last_source`` records ``"ccxt"`` or ``"synthetic"``.
        """
        symbol = symbol or self.settings.symbol
        timeframe = timeframe or self.settings.timeframe
        bars = bars or self.settings.bars
        seed = self.settings.seed if seed is None else seed

        if not self.force_synthetic:
            exchange = self._build_exchange()
            if exchange is not None:
                try:
                    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=bars)
                    frame = pd.DataFrame(
                        raw, columns=["ts", "open", "high", "low", "close", "volume"]
                    )
                    frame.index = pd.to_datetime(frame.pop("ts"), unit="ms", utc=True)
                    frame.index.name = None
                    if len(frame) >= 2:
                        self.last_source = "ccxt"
                        return frame.astype(float)
                except Exception:
                    pass  # any live failure degrades to the offline path (I6)

        self.last_source = "synthetic"
        return synthetic_ohlcv(symbol, timeframe, bars=bars, seed=seed)

    def snapshot(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
        bars: int | None = None,
        seed: int | None = None,
        include_channels: bool = False,
    ) -> MarketSnapshot:
        """Build a :class:`MarketSnapshot` for the committee.

        Args:
            include_channels: also attach deterministic synthetic
                derivatives/onchain/macro/sentiment channels (offline demo of a
                full-data snapshot; real channels arrive with the M2 lake).
        """
        symbol = symbol or self.settings.symbol
        timeframe = timeframe or self.settings.timeframe
        seed = self.settings.seed if seed is None else seed
        ohlcv = self.fetch_ohlcv(symbol, timeframe, bars, seed)
        channels: dict[str, Any] = {}
        if include_channels:
            channels = synthetic_channels(symbol, seed=seed)
        return MarketSnapshot(symbol=symbol, timeframe=timeframe, ohlcv=ohlcv, **channels)
