"""WP-7.6 — Confidence Calibration: stated vs realised, identity on cold start."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.committee.analysts import default_analysts
from quantos.committee.calibration import CalibratedConfidenceModel, ConfidenceCalibrator
from quantos.committee.committee import InvestmentCommittee
from quantos.data.models import MarketSnapshot
from quantos.memory import DecisionArchive
from tests.test_archive import fake_record


def archive_with(
    stated: float, wins: int, losses: int, regime: str = "TREND_UP"
) -> DecisionArchive:
    archive = DecisionArchive()
    day = 1
    for won in [True] * wins + [False] * losses:
        record = fake_record(as_of=f"2024-01-{day:02d}T00:00:00+00:00", regime=regime)
        record["confidence"] = stated
        record["reasons"] = [f"seed {day}"]  # vary content so ids differ
        archive.record_outcome(archive.record(record), pnl=1.0 if won else -1.0)
        day += 1
    return archive


class TestCalibrator:
    def test_cold_start_is_identity(self) -> None:
        calibrator = ConfidenceCalibrator()
        assert not calibrator.fitted
        assert calibrator.calibrate(0.9) == 0.9
        calibrator.fit(DecisionArchive())  # nothing closed — still identity
        assert not calibrator.fitted and calibrator.calibrate(0.42) == 0.42

    def test_overconfidence_is_deflated(self) -> None:
        """The acceptance: '90%' decisions that won ~60% map 0.90 -> ≈0.60."""
        calibrator = ConfidenceCalibrator().fit(archive_with(0.9, wins=12, losses=8))
        assert calibrator.fitted
        assert calibrator.calibrate(0.9) == pytest.approx(0.6, abs=0.05)

    def test_regime_aware_maps_differ(self) -> None:
        archive = archive_with(0.9, wins=8, losses=2, regime="TREND_UP")
        for record in archive_with(0.9, wins=2, losses=8, regime="RANGE").query():
            archive.record(record.decision)
            archive.record_outcome(archive.record(record.decision), record.pnl or 0.0)
        calibrator = ConfidenceCalibrator().fit(archive)
        trend = calibrator.calibrate(0.9, {"regime": {"label": "TREND_UP"}})
        rng = calibrator.calibrate(0.9, {"regime": {"label": "RANGE"}})
        assert trend == pytest.approx(0.8, abs=0.05)
        assert rng == pytest.approx(0.2, abs=0.05)

    def test_map_is_monotonic(self) -> None:
        archive = archive_with(0.9, wins=6, losses=4)
        for record in archive_with(0.5, wins=9, losses=1).query():  # lower stated, higher win
            archive.record(record.decision)
            archive.record_outcome(archive.record(record.decision), record.pnl or 0.0)
        calibrator = ConfidenceCalibrator().fit(archive)
        assert calibrator.calibrate(0.9) >= calibrator.calibrate(0.5)

    def test_reliability_bins_for_the_dashboard(self) -> None:
        calibrator = ConfidenceCalibrator().fit(archive_with(0.9, wins=12, losses=8))
        bins = calibrator.reliability()
        assert len(bins) == calibrator.n_bins
        hot = bins[9]  # the 0.9 bin
        assert hot["n"] == 20.0 and hot["realised_rate"] == pytest.approx(0.6)


class TestWiring:
    def test_drops_into_the_committee_without_core_edits(self, uptrend_ohlcv: pd.DataFrame) -> None:
        """I7: a calibrated model is just another confidence_model."""
        calibrator = ConfidenceCalibrator().fit(archive_with(0.9, wins=2, losses=18))
        committee = InvestmentCommittee(
            analysts=default_analysts(),
            confidence_model=CalibratedConfidenceModel(calibrator),
        )
        snapshot = MarketSnapshot(
            "BTC/USDT",
            "1h",
            uptrend_ohlcv,
            macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
            sentiment={"score": 0.6},
            onchain={"whale_accumulation": 0.8},
        )
        decision = committee.deliberate(snapshot)
        # history says high-stated calls win ~10% — the calibrated composite
        # collapses and the (previously approving) bench must stand down.
        assert decision.confidence <= 0.2
        assert not decision.approved
