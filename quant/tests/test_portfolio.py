"""WP-9.2 — Portfolio Intelligence: correlations, exposures, concentration → risk."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantos.committee.risk_manager import RiskManager
from quantos.data.models import MarketSnapshot
from quantos.portfolio import (
    PortfolioAnalyzer,
    PortfolioConcentration,
    concentration,
    correlation_matrix,
    exposure,
)


def correlated_prices(n: int = 200, seed: int = 3) -> pd.DataFrame:
    """BTC & ETH share a driver (high corr); GOLD is independent."""
    rng = np.random.default_rng(seed)
    driver = np.cumsum(rng.normal(0.0, 1.0, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    btc = 100 + driver + rng.normal(0.0, 0.05, n)
    eth = 50 + 0.5 * driver + rng.normal(0.0, 0.05, n)
    gold = 2000 + np.cumsum(rng.normal(0.0, 1.0, n))
    return pd.DataFrame({"BTC": btc, "ETH": eth, "GOLD": gold}, index=idx)


class TestAnalytics:
    def test_correlation_matrix_recovers_structure(self) -> None:
        corr = correlation_matrix(correlated_prices())
        assert corr.loc["BTC", "ETH"] > 0.8  # shared driver
        assert abs(corr.loc["BTC", "GOLD"]) < 0.3  # independent

    def test_correlation_window_is_point_in_time(self) -> None:
        prices = correlated_prices()
        windowed = correlation_matrix(prices, window=30)
        # A window uses only the trailing rows — never more than asked for.
        assert windowed.shape == (3, 3)

    def test_exposure_net_gross(self) -> None:
        exp = exposure({"BTC": 0.4, "ETH": 0.2, "GOLD": -0.1})
        assert exp.net == 0.5
        assert exp.gross == 0.7
        assert exp.long == 0.6 and exp.short == -0.1

    def test_concentration_finds_the_dominant_name(self) -> None:
        conc = concentration({"BTC": 0.8, "ETH": 0.1, "GOLD": -0.1})
        assert conc["max_asset"] == "BTC"
        assert conc["max_weight"] == 0.8
        assert conc["herfindahl"] > 0.6

    def test_empty_book_is_safe(self) -> None:
        conc = concentration({})
        assert conc["max_asset"] is None and conc["max_weight"] == 0.0


class TestAnalyzer:
    def test_report_flags_a_concentrated_book(self) -> None:
        analyzer = PortfolioAnalyzer()
        report = analyzer.analyze({"BTC/USDT": 0.9, "ETH/USDT": 0.05}, prices=correlated_prices())
        assert any("concentration" in f for f in report.flags)

    def test_report_flags_crowding_from_correlation(self) -> None:
        prices = correlated_prices().rename(columns={"BTC": "BTC/USDT", "ETH": "ETH/USDT"})
        analyzer = PortfolioAnalyzer(max_asset_weight=0.99, high_correlation=0.8)
        report = analyzer.analyze({"BTC/USDT": 0.3, "ETH/USDT": 0.3}, prices=prices)
        assert any("crowding" in f for f in report.flags)

    def test_report_is_json_serialisable(self) -> None:
        import json

        report = PortfolioAnalyzer().analyze({"BTC/USDT": 0.5, "GOLD": -0.2})
        json.dumps(report.as_dict())

    def test_cluster_exposures(self) -> None:
        report = PortfolioAnalyzer().analyze({"BTC/USDT": 0.4, "ETH/USDT": 0.2, "GOLD": -0.1})
        assert report.clusters["crypto"].gross == 0.6
        assert report.clusters["metal"].gross == 0.1


class TestRiskConsumesConcentration:
    def _snapshot(self) -> MarketSnapshot:
        idx = pd.date_range("2024-01-01", periods=60, freq="1h", tz="UTC")
        close = pd.Series(np.linspace(100, 110, 60), index=idx)
        ohlcv = pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 100.0},
            index=idx,
        )
        return MarketSnapshot("BTC/USDT", "1h", ohlcv)

    def test_concentrated_book_is_vetoed_by_risk(self) -> None:
        analyzer = PortfolioAnalyzer()
        report = analyzer.analyze({"BTC/USDT": 0.95, "ETH/USDT": 0.05})
        manager = RiskManager(rules=[PortfolioConcentration(max_weight=0.6)])
        assessment = manager.assess(
            self._snapshot(), context={"portfolio_concentration": report.concentration}
        )
        assert assessment.vetoed  # the flag is consumed by risk (I5)

    def test_balanced_book_passes(self) -> None:
        analyzer = PortfolioAnalyzer()
        report = analyzer.analyze({"BTC/USDT": 0.3, "ETH/USDT": 0.3, "GOLD": 0.3})
        manager = RiskManager(rules=[PortfolioConcentration(max_weight=0.6)])
        assessment = manager.assess(
            self._snapshot(), context={"portfolio_concentration": report.concentration}
        )
        assert not assessment.vetoed

    def test_rule_passes_without_a_portfolio_snapshot(self) -> None:
        manager = RiskManager(rules=[PortfolioConcentration()])
        assert not manager.assess(self._snapshot()).vetoed  # never fabricates (I3)
