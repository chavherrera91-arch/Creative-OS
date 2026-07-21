"""Hermes contracts — events, channels and the read-only messenger (module 24).

Hermes is the platform's *presentation* voice: it pushes concise alerts
(decisions, vetoes, regime changes, anomalies, digests) and answers questions
from the recorded history. It is **strictly read-only** (I1): nothing in this
package imports the execution or paper layers, and the agent exposes no way
to place an order or mutate platform state — a guard test enforces both.

Delivery is routed per event kind, de-duplicated, and rate-limited with an
injectable clock so behaviour is deterministic under test (I8).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["Channel", "HermesAgent", "HermesEvent", "Notifier", "format_alert"]

#: The event kinds Hermes understands (routing keys).
EVENT_KINDS = ("decision", "veto", "regime_change", "anomaly", "digest", "hypothesis")


@dataclass(frozen=True)
class HermesEvent:
    """One noteworthy platform occurrence, ready to deliver.

    Attributes:
        kind: routing key, one of :data:`EVENT_KINDS`.
        title: one-line headline.
        body: the alert body (usually the recorded explanation, I4).
        payload: structured extras for machine consumers.
        dedupe_key: identical keys are delivered at most once.
    """

    kind: str
    title: str
    body: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {self.kind!r} (expected {EVENT_KINDS})")


def format_alert(event: HermesEvent) -> str:
    """The canonical alert text every channel sends."""
    header = f"[quantos][{event.kind.upper()}] {event.title}"
    return f"{header}\n{event.body}" if event.body else header


@runtime_checkable
class Channel(Protocol):
    """Somewhere an alert can be delivered (console, Telegram, ...)."""

    name: str

    def send(self, message: str) -> None:
        """Deliver one formatted alert."""
        ...


class Notifier:
    """Route events to channels with de-duplication and rate limiting.

    Args:
        channels: default channels every event goes to.
        routes: per-kind channel overrides (kind -> channels).
        max_per_window: per-kind delivery budget inside ``window_seconds``.
        window_seconds: the rate-limit window.
        clock: injectable monotonic clock (deterministic tests, I8).
    """

    def __init__(
        self,
        channels: list[Channel],
        routes: dict[str, list[Channel]] | None = None,
        *,
        max_per_window: int = 20,
        window_seconds: float = 3600.0,
        clock: Any = time.monotonic,
    ) -> None:
        self.channels = list(channels)
        self.routes = dict(routes or {})
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self._clock = clock
        self._sent_keys: set[str] = set()
        self._deliveries: dict[str, list[float]] = {}

    def notify(self, event: HermesEvent) -> bool:
        """Deliver ``event``; returns False when deduped or rate-limited."""
        if event.dedupe_key:
            if event.dedupe_key in self._sent_keys:
                return False
            self._sent_keys.add(event.dedupe_key)

        now = float(self._clock())
        window = self._deliveries.setdefault(event.kind, [])
        window[:] = [t for t in window if now - t < self.window_seconds]
        if len(window) >= self.max_per_window:
            return False
        window.append(now)

        message = format_alert(event)
        for channel in self.routes.get(event.kind, self.channels):
            channel.send(message)
        return True


@runtime_checkable
class HermesAgent(Protocol):
    """The messenger: pushes events out, answers questions from the record.

    STRICTLY read-only — informs and answers; never places an order or
    changes a limit (I1). Answers come from the DecisionArchive / RAG
    memory's already-recorded explanations, never fresh analysis.
    """

    def on_event(self, event: HermesEvent) -> None:
        """Push one event through the notifier."""
        ...

    def answer(self, question: str) -> str:
        """Answer a natural-language question over the archived record."""
        ...
