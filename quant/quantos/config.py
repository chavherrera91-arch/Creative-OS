"""Central configuration.

``Settings`` is an immutable record with safe offline defaults. Values can be
overridden from the environment (``QUANTOS_*`` variables — see
``.env.example``); no secret is ever required for research (invariant I6).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields

__all__ = ["Settings"]

_ENV_PREFIX = "QUANTOS_"


@dataclass(frozen=True)
class Settings:
    """Platform settings with offline-safe defaults.

    Attributes:
        exchange_id: ccxt exchange id used for *read-only* market data.
        symbol: default trading pair researched.
        timeframe: default bar timeframe.
        bars: default number of bars in a snapshot.
        seed: global random seed — everything derives from it (I8).
        fee_bps: taker fee, basis points per fill.
        slippage_bps: assumed slippage, basis points per fill.
        initial_cash: paper-trading starting equity (I1: paper only).
        confidence_threshold: minimum composite confidence to trade.
        min_agreement: minimum weighted analyst agreement to trade.
        max_position_fraction: max fraction of equity a paper order may use.
        lake_root: directory the Data Lake persists under (M2); relative to
            the working directory by default, overridable via
            ``QUANTOS_LAKE_ROOT``.
    """

    exchange_id: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    bars: int = 400
    seed: int = 42
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    initial_cash: float = 100_000.0
    confidence_threshold: float = 0.35
    min_agreement: float = 0.5
    max_position_fraction: float = 0.25
    lake_root: str = ".quantos-lake"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``QUANTOS_*`` environment variables.

        Args:
            env: mapping to read from; defaults to ``os.environ``.

        Returns:
            A ``Settings`` where each field may be overridden by
            ``QUANTOS_<FIELDNAME>`` (upper-cased), falling back to the default.
        """
        source = os.environ if env is None else env
        overrides: dict[str, object] = {}
        for field in fields(cls):
            raw = source.get(_ENV_PREFIX + field.name.upper())
            if raw is None:
                continue
            if field.type in ("int", int):
                overrides[field.name] = int(raw)
            elif field.type in ("float", float):
                overrides[field.name] = float(raw)
            else:
                overrides[field.name] = raw
        return cls(**overrides)  # type: ignore[arg-type]

    def as_dict(self) -> dict[str, object]:
        """JSON-serialisable representation (pinned into run manifests, I8)."""
        return asdict(self)
