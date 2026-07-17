"""WP-1.4 — confidence aggregation: thresholds, agreement, abstention (I3)."""

from __future__ import annotations

import json

import pytest

from quantos.committee.base import AnalystOpinion, Direction, Evidence
from quantos.committee.confidence import ConfidenceModel


def opinion(
    category: str,
    direction: Direction,
    confidence: float,
    abstained: bool = False,
) -> AnalystOpinion:
    return AnalystOpinion(
        analyst=f"{category}-analyst",
        category=category,
        direction=direction,
        confidence=0.0 if abstained else confidence,
        evidence=[Evidence(name="e", detail="test evidence", impact=0.0)],
        abstained=abstained,
    )


class TestAggregation:
    def test_unanimous_long_clears_threshold(self) -> None:
        report = ConfidenceModel(threshold=0.5, min_agreement=0.6).aggregate(
            [
                opinion("technical", Direction.LONG, 0.8),
                opinion("statistical", Direction.LONG, 0.7),
                opinion("macro", Direction.LONG, 0.6),
            ]
        )
        assert report.direction is Direction.LONG
        assert report.confidence > 0.5
        assert report.agreement == 1.0
        assert report.meets_threshold

    def test_disagreement_lowers_agreement_and_blocks(self) -> None:
        model = ConfidenceModel(threshold=0.2, min_agreement=0.9)
        report = model.aggregate(
            [
                opinion("technical", Direction.LONG, 0.9),
                opinion("statistical", Direction.SHORT, 0.2),
                opinion("macro", Direction.SHORT, 0.2),
            ]
        )
        assert report.agreement < 0.9
        assert not report.meets_threshold  # agreement bar fails even if confidence clears

    def test_below_confidence_threshold_blocks(self) -> None:
        report = ConfidenceModel(threshold=0.6, min_agreement=0.5).aggregate(
            [opinion("technical", Direction.LONG, 0.3)]
        )
        assert report.direction is Direction.LONG
        assert not report.meets_threshold

    def test_opposing_high_conviction_nets_to_flat(self) -> None:
        report = ConfidenceModel().aggregate(
            [
                opinion("technical", Direction.LONG, 0.8),
                opinion("statistical", Direction.SHORT, 0.8),
            ]
        )
        assert report.direction is Direction.FLAT
        assert not report.meets_threshold


class TestAbstention:
    """I3: abstentions are excluded from the denominator."""

    def test_all_abstain_is_flat(self) -> None:
        report = ConfidenceModel().aggregate(
            [
                opinion("macro", Direction.FLAT, 0.0, abstained=True),
                opinion("sentiment", Direction.FLAT, 0.0, abstained=True),
            ]
        )
        assert report.direction is Direction.FLAT
        assert report.confidence == 0.0
        assert report.n_active == 0
        assert not report.meets_threshold
        assert len(report.abstentions) == 2

    def test_abstentions_do_not_dilute_conviction(self) -> None:
        model = ConfidenceModel(threshold=0.5, min_agreement=0.5)
        with_abstainers = model.aggregate(
            [
                opinion("technical", Direction.LONG, 0.8),
                opinion("macro", Direction.FLAT, 0.0, abstained=True),
                opinion("sentiment", Direction.FLAT, 0.0, abstained=True),
                opinion("onchain", Direction.FLAT, 0.0, abstained=True),
            ]
        )
        alone = model.aggregate([opinion("technical", Direction.LONG, 0.8)])
        assert with_abstainers.confidence == pytest.approx(alone.confidence)
        assert with_abstainers.confidence == pytest.approx(0.8)
        assert with_abstainers.abstentions == [
            "macro-analyst",
            "sentiment-analyst",
            "onchain-analyst",
        ]


class TestWeightsAndSerialisation:
    def test_category_weights_matter(self) -> None:
        # technical (w=1.0) LONG 0.6 vs sentiment (w=0.6) SHORT 0.6:
        # composite = (0.6 - 0.36) / 1.6 > 0 -> LONG
        report = ConfidenceModel().aggregate(
            [
                opinion("technical", Direction.LONG, 0.6),
                opinion("sentiment", Direction.SHORT, 0.6),
            ]
        )
        assert report.direction is Direction.LONG

    def test_report_serialisable_and_deterministic(self) -> None:
        opinions = [
            opinion("technical", Direction.LONG, 0.7),
            opinion("macro", Direction.FLAT, 0.0, abstained=True),
        ]
        model = ConfidenceModel()
        a, b = model.aggregate(opinions), model.aggregate(opinions)
        assert a.as_dict() == b.as_dict()
        json.dumps(a.as_dict())
        assert a.per_category["technical"]["signed_score"] == pytest.approx(0.7)
