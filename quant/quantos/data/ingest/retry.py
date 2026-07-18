"""Retry policy (exponential backoff + jitter) and circuit breaker.

Both are dependency-free and fully injectable: the sleep function and the
clock are parameters, so tests exercise every path deterministically without
ever sleeping (I6/I8).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ["CircuitBreaker", "RetryPolicy"]


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with optional jitter.

    Attributes:
        max_attempts: total attempts (first try included).
        base_delay: delay before the second attempt, in seconds.
        max_delay: backoff cap, in seconds.
        jitter: multiply each delay by a uniform factor in [0.5, 1.5]
            (decorrelates a thundering herd of connectors).
    """

    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True

    def delay(self, attempt: int, rng: np.random.Generator | None = None) -> float:
        """Backoff delay after a failed attempt (1-based).

        Args:
            attempt: the attempt number that just failed (1 = first try).
            rng: seeded generator for the jitter factor (deterministic tests,
                I8); a fresh generator is used when omitted.
        """
        if attempt < 1:
            raise ValueError("attempt is 1-based")
        raw = min(self.max_delay, self.base_delay * (2.0 ** (attempt - 1)))
        if not self.jitter:
            return raw
        factor = float((rng or np.random.default_rng()).uniform(0.5, 1.5))
        return raw * factor

    def call(
        self,
        fn: Callable[[], Any],
        *,
        sleep: Callable[[float], None] = time.sleep,
        rng: np.random.Generator | None = None,
    ) -> Any:
        """Run ``fn`` under this policy, backing off between failures.

        Raises:
            Exception: the last error, once ``max_attempts`` are exhausted.
        """
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 — every failure is retryable here
                last = exc
                if attempt < self.max_attempts:
                    sleep(self.delay(attempt, rng))
        assert last is not None
        raise last


class CircuitBreaker:
    """Stops hammering a failing source; lets one probe through after a cool-off.

    States: ``closed`` (normal), ``open`` (rejecting) and ``half_open``
    (cool-off elapsed — one probe allowed; success closes, failure re-opens).
    A failing connector therefore degrades gracefully and never blocks the
    ingestion of the others.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Args:
            failure_threshold: consecutive failures that open the circuit.
            reset_timeout: seconds before a half-open probe is allowed.
            clock: monotonic time source (injectable for tests).
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        """Current state: ``closed | open | half_open``."""
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.reset_timeout:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        """True when a call may proceed (closed, or a half-open probe)."""
        return self.state != "open"

    def record(self, ok: bool) -> None:
        """Record a call outcome; success closes, failures accumulate/open."""
        if ok:
            self._failures = 0
            self._opened_at = None
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable state (surfaced in health reports)."""
        return {
            "state": self.state,
            "failures": self._failures,
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }
