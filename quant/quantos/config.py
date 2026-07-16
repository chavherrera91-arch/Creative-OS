"""Central configuration.

Settings are plain dataclasses with sane defaults, optionally overridden from
environment variables (and a ``.env`` file if present). No secrets are required
for research mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal, dependency-free ``.env`` loader. Existing env vars win."""
    env_path = Path(os.getenv("QUANTOS_ENV_FILE", ".env"))
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class CommitteeConfig:
    """Thresholds governing when the committee is allowed to act."""

    confidence_threshold: float = 0.60
    agreement_threshold: float = 0.55
    # Relative importance of each analyst category in the composite score.
    category_weights: dict[str, float] = field(
        default_factory=lambda: {
            "technical": 1.0,
            "macro": 0.9,
            "sentiment": 0.6,
            "onchain": 0.8,
            "statistical": 0.9,
        }
    )


@dataclass(frozen=True)
class RiskConfig:
    """Hard limits the Risk Manager enforces via veto."""

    max_daily_drawdown: float = 0.02
    vol_zscore_veto: float = 3.0
    min_liquidity_ratio: float = 0.25


@dataclass(frozen=True)
class Settings:
    data_source: str = "auto"  # auto | ccxt | synthetic
    live_trading: str = "DISABLED"
    committee: CommitteeConfig = field(default_factory=CommitteeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def live_trading_enabled(self) -> bool:
        # Deliberately strict: only an explicit, exact opt-in could ever flip
        # this, and even then execution stays disabled in this phase.
        return False


def load_settings() -> Settings:
    """Build :class:`Settings` from defaults + environment overrides."""
    _load_dotenv()
    committee = CommitteeConfig(
        confidence_threshold=_get_float("QUANTOS_CONFIDENCE_THRESHOLD", 0.60),
        agreement_threshold=_get_float("QUANTOS_AGREEMENT_THRESHOLD", 0.55),
    )
    risk = RiskConfig(
        max_daily_drawdown=_get_float("QUANTOS_MAX_DAILY_DRAWDOWN", 0.02),
        vol_zscore_veto=_get_float("QUANTOS_VOL_ZSCORE_VETO", 3.0),
    )
    return Settings(
        data_source=os.getenv("QUANTOS_DATA_SOURCE", "auto"),
        live_trading=os.getenv("QUANTOS_LIVE_TRADING", "DISABLED"),
        committee=committee,
        risk=risk,
    )
