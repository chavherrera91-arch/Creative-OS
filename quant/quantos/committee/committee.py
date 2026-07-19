"""The Investment Committee orchestrator (module 2, M1 flow; M4 market state).

Analysts run independently, the confidence model aggregates, the Risk Manager
screens, the Chair decides — simple and fully deterministic (the optional
debate protocol is M6). ``default_committee()`` wires the standard bench;
``regime_aware_committee()`` adds the M4 market-state layer: the deliberation
context is enriched with the classified ``regime`` and the active
``anomalies`` (ARCHITECTURE §4), the Chair's regime gate can stand the
committee down, and both are recorded in the decision (I4).
"""

from __future__ import annotations

from typing import Any

import quantos
from quantos.anomaly.base import AnomalyDetector, anomaly_summary
from quantos.anomaly.detectors import ZScoreDetector
from quantos.committee.analysts import AnomalyAnalyst, default_analysts
from quantos.committee.base import Analyst
from quantos.committee.chair import Chair
from quantos.committee.confidence import ConfidenceModel
from quantos.committee.decision import CommitteeDecision
from quantos.committee.risk_manager import RiskManager
from quantos.config import Settings
from quantos.data.models import MarketSnapshot
from quantos.regime.base import RegimeClassifier
from quantos.regime.classifier import RuleRegimeClassifier

__all__ = ["InvestmentCommittee", "default_committee", "regime_aware_committee"]


class InvestmentCommittee:
    """Composes analysts, confidence model, risk manager and chair (I7)."""

    def __init__(
        self,
        analysts: list[Analyst],
        confidence_model: ConfidenceModel | None = None,
        risk_manager: RiskManager | None = None,
        chair: Chair | None = None,
        settings: Settings | None = None,
        regime_classifier: RegimeClassifier | None = None,
        anomaly_detector: AnomalyDetector | None = None,
    ) -> None:
        """
        Args:
            analysts: the specialist bench.
            confidence_model: aggregation model (settings-derived default).
            risk_manager: the veto-holding screen (I5).
            chair: the deciding chair.
            settings: platform settings.
            regime_classifier: optional M4 Market Regime Engine; when set,
                every deliberation classifies the snapshot and injects the
                :class:`~quantos.regime.base.RegimeState` record into the
                context as ``regime`` (unless the caller already supplied one).
            anomaly_detector: optional M4 anomaly detector; when set, the
                point-in-time anomaly summary is injected as ``anomalies``.
        """
        self.settings = settings or Settings()
        self.analysts = analysts
        self.confidence_model = confidence_model or ConfidenceModel(
            threshold=self.settings.confidence_threshold,
            min_agreement=self.settings.min_agreement,
        )
        self.risk_manager = risk_manager or RiskManager()
        self.chair = chair or Chair()
        self.regime_classifier = regime_classifier
        self.anomaly_detector = anomaly_detector

    def _run_manifest(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        """Pin everything needed to replay this deliberation (I8).

        Deterministic on purpose: derived from the snapshot's own point in
        time, never from a wall clock.
        """
        return {
            "quantos_version": quantos.__version__,
            "seed": self.settings.seed,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "bars": snapshot.bars,
            "as_of": snapshot.as_of,
            "analysts": [a.name for a in self.analysts],
            "regime_classifier": (
                type(self.regime_classifier).__name__ if self.regime_classifier else None
            ),
            "anomaly_detector": (
                type(self.anomaly_detector).__name__ if self.anomaly_detector else None
            ),
            "weights": dict(self.confidence_model.weights),
            "confidence_threshold": self.confidence_model.threshold,
            "min_agreement": self.confidence_model.min_agreement,
            "settings": self.settings.as_dict(),
        }

    def _enrich_context(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Inject the M4 market-state layer into the deliberation context.

        The regime classification and anomaly summary are computed from the
        snapshot only (I2) and injected under ``regime`` / ``anomalies``
        unless the caller already supplied them — an outer orchestrator
        (ARCHITECTURE §4) always wins.
        """
        context = dict(context or {})
        if self.regime_classifier is not None and "regime" not in context:
            context["regime"] = self.regime_classifier.classify(snapshot).as_dict()
        if self.anomaly_detector is not None and "anomalies" not in context:
            context["anomalies"] = anomaly_summary(self.anomaly_detector, snapshot.ohlcv)
        return context

    def deliberate(
        self, snapshot: MarketSnapshot, context: dict[str, Any] | None = None
    ) -> CommitteeDecision:
        """Run the full decision flow on a snapshot.

        Args:
            snapshot: the market view (analysts read only what is inside, I2).
            context: optional orchestration context (``regime``, ``anomalies``,
                ``daily_pnl_pct``, ``macro_event``, ``strategies_considered``...).

        Returns:
            A complete, auditable, reproducible :class:`CommitteeDecision`.
        """
        context = self._enrich_context(snapshot, context)
        opinions = [analyst.analyze(snapshot, context) for analyst in self.analysts]
        report = self.confidence_model.aggregate(opinions)
        risk = self.risk_manager.assess(snapshot, report, context)
        return self.chair.decide(
            snapshot,
            opinions,
            report,
            risk,
            context=context,
            run_manifest=self._run_manifest(snapshot),
        )


def default_committee(settings: Settings | None = None) -> InvestmentCommittee:
    """The standard M1 committee: five specialists, default thresholds."""
    return InvestmentCommittee(analysts=default_analysts(), settings=settings)


def regime_aware_committee(
    settings: Settings | None = None,
    regime_classifier: RegimeClassifier | None = None,
    anomaly_detector: AnomalyDetector | None = None,
) -> InvestmentCommittee:
    """The M4 market-state committee (ARCHITECTURE §4 flow, pre-Meta-Learner).

    The standard bench plus the :class:`~quantos.committee.analysts.AnomalyAnalyst`,
    with the rule Regime Engine and the z-score anomaly detector enriching
    every deliberation: the decision records the classified regime and any
    active anomalies (I4), and the Chair's regime gate stands down in an
    untradeable regime. Strategy selection per regime arrives with the
    Meta-Learner (M7).
    """
    detector = anomaly_detector or ZScoreDetector()
    return InvestmentCommittee(
        analysts=[*default_analysts(), AnomalyAnalyst(detector=detector)],
        settings=settings,
        regime_classifier=regime_classifier or RuleRegimeClassifier(),
        anomaly_detector=detector,
    )
