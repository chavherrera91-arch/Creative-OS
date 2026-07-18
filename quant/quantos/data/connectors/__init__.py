"""Data-source plug-ins (M2). Importing this package discovers every connector.

Discovery is dynamic: every non-private module in the package is imported so
its ``@register`` decorators run. Adding a new source is therefore *one new
file* — no edit to this package, the registry, or the lake (I7).
"""

from __future__ import annotations

import importlib
import pkgutil

from quantos.data.connectors.base import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
    HealthStatus,
)
from quantos.data.connectors.registry import ConnectorRegistry, register, registry

__all__ = [
    "Connector",
    "ConnectorMetadata",
    "ConnectorRegistry",
    "FetchRequest",
    "FetchResult",
    "HealthStatus",
    "register",
    "registry",
]

_CORE_MODULES = {"base", "registry"}

for _info in pkgutil.iter_modules(__path__):
    if _info.name in _CORE_MODULES or _info.name.startswith("_"):
        continue
    importlib.import_module(f"{__name__}.{_info.name}")
