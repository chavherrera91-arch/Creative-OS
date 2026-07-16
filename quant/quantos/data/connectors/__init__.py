"""Data-source connectors.

Importing this package registers the built-in connectors (each module calls
``@register`` at import time). Third-party connectors self-register the same way
— no core edit required.
"""

from quantos.data.connectors.base import (
    Connector,
    ConnectorMetadata,
    FetchRequest,
    FetchResult,
    HealthStatus,
)
from quantos.data.connectors.registry import (
    ConnectorRegistry,
    register,
    registry,
)

# Built-in connectors self-register on import; they are pulled in by
# quantos.data.connectors.builtins so third-party connectors can register the
# same way without any core edit.
from quantos.data.connectors import builtins  # noqa: E402,F401

__all__ = [
    "Connector",
    "ConnectorMetadata",
    "FetchRequest",
    "FetchResult",
    "HealthStatus",
    "ConnectorRegistry",
    "register",
    "registry",
]
