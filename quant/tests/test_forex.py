"""Forex data — real via yfinance, honest synthetic fallback (I3/I6)."""

from __future__ import annotations

from quantos.data.forex import fetch_forex_ohlcv, to_yahoo_symbol
from quantos.mining import StrategyMiner, StrategyVault


def test_yahoo_symbol_mapping() -> None:
    assert to_yahoo_symbol("EUR/USD") == "EURUSD=X"
    assert to_yahoo_symbol("gbp/jpy") == "GBPJPY=X"


def test_synthetic_fallback_is_labelled_and_usable() -> None:
    frame, source = fetch_forex_ohlcv("EUR/USD", force_synthetic=True)
    assert source == "synthetic"  # never claims 'real' offline (I3)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) > 60
    assert 0.5 < float(frame["close"].iloc[-1]) < 3.0  # forex-scale prices, not 50k


def test_miner_can_mine_forex_offline(tmp_path) -> None:
    # force_synthetic keeps it offline; market='forex' just picks the source.
    vault = StrategyVault(path=tmp_path / "v.json")
    miner = StrategyMiner(
        vault=vault, symbol="EUR/USD", market="forex", force_synthetic=True, n_candidates=30
    )
    summary = miner.dig(0)
    assert summary["tested"] == 30
    assert summary["vault_size"] == len(vault)
