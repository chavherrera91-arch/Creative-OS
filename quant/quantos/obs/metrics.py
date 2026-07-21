"""Runtime metrics — in-house counters with Prometheus text exposition.

The paper engine and the lake's ingestors increment plain in-memory
:class:`Counter`/:class:`Gauge` objects (no dependency, no server, I6). The
registry renders the standard Prometheus text format on demand, so a real
Prometheus can scrape it when the infra exists — but nothing here ever
requires one. ``prometheus-client`` (the ``[obs]`` extra) is intentionally
not imported: the exposition format is stable and trivially rendered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["Counter", "Gauge", "MetricsRegistry", "metrics"]


def _labels_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def _render_labels(key: tuple[tuple[str, str], ...]) -> str:
    if not key:
        return ""
    inner = ",".join(f'{name}="{value}"' for name, value in key)
    return "{" + inner + "}"


@dataclass
class Counter:
    """A monotonically increasing metric (per label set).

    Attributes:
        name: Prometheus metric name (e.g. ``quantos_paper_trades_total``).
        help: one-line description rendered as ``# HELP``.
    """

    name: str
    help: str = ""
    _values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict, repr=False)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increase the counter; negative increments are rejected."""
        if amount < 0:
            raise ValueError("counters only go up")
        key = _labels_key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(_labels_key(labels), 0.0)

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key in sorted(self._values):
            lines.append(f"{self.name}{_render_labels(key)} {self._values[key]}")
        return "\n".join(lines)


@dataclass
class Gauge:
    """A set-to-current-value metric (per label set)."""

    name: str
    help: str = ""
    _values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict, repr=False)

    def set(self, value: float, **labels: str) -> None:
        self._values[_labels_key(labels)] = float(value)

    def value(self, **labels: str) -> float:
        return self._values.get(_labels_key(labels), 0.0)

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        for key in sorted(self._values):
            lines.append(f"{self.name}{_render_labels(key)} {self._values[key]}")
        return "\n".join(lines)


class MetricsRegistry:
    """Create-or-get metrics by name; render them all for scraping."""

    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Gauge] = {}

    def counter(self, name: str, help: str = "") -> Counter:
        """Get (or create) the counter ``name``."""
        metric = self._metrics.setdefault(name, Counter(name=name, help=help))
        if not isinstance(metric, Counter):
            raise TypeError(f"metric {name!r} is a {type(metric).__name__}, not a Counter")
        return metric

    def gauge(self, name: str, help: str = "") -> Gauge:
        """Get (or create) the gauge ``name``."""
        metric = self._metrics.setdefault(name, Gauge(name=name, help=help))
        if not isinstance(metric, Gauge):
            raise TypeError(f"metric {name!r} is a {type(metric).__name__}, not a Gauge")
        return metric

    def render(self) -> str:
        """The whole registry in Prometheus text exposition format."""
        return "\n".join(self._metrics[name].render() for name in sorted(self._metrics)) + "\n"

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot for the dashboard / Hermes digests."""
        out: dict[str, Any] = {}
        for name in sorted(self._metrics):
            metric = self._metrics[name]
            out[name] = {
                _render_labels(key) or "_": value for key, value in sorted(metric._values.items())
            }
        return out


#: Process-wide default registry (the paper engine and ingestors write here).
metrics = MetricsRegistry()
