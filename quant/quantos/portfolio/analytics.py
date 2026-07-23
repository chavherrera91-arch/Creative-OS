"""Portfolio analytics — correlations, exposures, concentration (pure funcs).

All inputs are *history up to the as-of bar* (the caller slices; nothing here
peeks past the frame it is handed, I2) and every function is a deterministic
function of its inputs (I8). Positions are signed fractions of equity: ``+0.2``
is a 20%-of-equity long, ``-0.1`` a 10% short.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

__all__ = ["Exposure", "concentration", "correlation_matrix", "exposure", "group_exposures"]


def correlation_matrix(prices: pd.DataFrame, window: int | None = None) -> pd.DataFrame:
    """Correlation of per-asset returns, optionally over the trailing window.

    Args:
        prices: one column of prices per asset, time-indexed ascending.
        window: use only the last ``window`` returns when given (point-in-time).

    Returns:
        A symmetric correlation matrix (assets × assets); a lone asset
        correlates 1.0 with itself.
    """
    returns = prices.astype(float).pct_change().dropna(how="all")
    if window is not None:
        returns = returns.tail(window)
    return returns.corr()


@dataclass(frozen=True)
class Exposure:
    """Net / gross / long / short book exposure (fractions of equity).

    Attributes:
        net: signed sum of positions (directional tilt).
        gross: sum of absolute positions (leverage).
        long: sum of the long legs.
        short: sum of the short legs (negative).
    """

    net: float
    gross: float
    long: float
    short: float

    def as_dict(self) -> dict[str, float]:
        """JSON-serialisable representation."""
        return {"net": self.net, "gross": self.gross, "long": self.long, "short": self.short}


def exposure(positions: Mapping[str, float]) -> Exposure:
    """Aggregate signed positions into net/gross/long/short exposure."""
    longs = sum(float(w) for w in positions.values() if w > 0)
    shorts = sum(float(w) for w in positions.values() if w < 0)
    return Exposure(
        net=round(longs + shorts, 10),
        gross=round(longs - shorts, 10),
        long=round(longs, 10),
        short=round(shorts, 10),
    )


def group_exposures(
    positions: Mapping[str, float], groups: Mapping[str, str]
) -> dict[str, Exposure]:
    """Exposure per cluster/factor (``groups`` maps asset → group name)."""
    buckets: dict[str, dict[str, float]] = {}
    for asset, weight in positions.items():
        group = groups.get(asset, "unclassified")
        buckets.setdefault(group, {})[asset] = float(weight)
    return {group: exposure(book) for group, book in sorted(buckets.items())}


def concentration(positions: Mapping[str, float]) -> dict[str, Any]:
    """Concentration of the book by gross weight.

    Returns the Herfindahl index (``1/n`` fully diversified → ``1.0`` all in
    one name), the single largest gross weight and which asset holds it — the
    inputs the Risk Manager's concentration limit consumes.
    """
    gross = sum(abs(float(w)) for w in positions.values())
    if gross <= 0.0:
        return {"herfindahl": 0.0, "max_weight": 0.0, "max_asset": None, "gross": 0.0}
    weights = {a: abs(float(w)) / gross for a, w in positions.items()}
    max_asset = max(weights, key=lambda a: (weights[a], a))
    return {
        "herfindahl": round(sum(w * w for w in weights.values()), 10),
        "max_weight": round(weights[max_asset], 10),
        "max_asset": max_asset,
        "gross": round(gross, 10),
    }
