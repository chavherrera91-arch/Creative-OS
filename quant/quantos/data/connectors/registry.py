"""Connector registry with self-registration.

The module-level :data:`registry` is discovered by the DataLake; connectors add
themselves to it via the :func:`register` class decorator. Because discovery is
registry-based, a new source is added by writing one decorated module — the core
(lake, runner, catalog) never names a specific connector (invariant I7).
"""

from __future__ import annotations

from quantos.data.connectors.base import Connector


class ConnectorRegistry:
    """Holds the process-wide set of available connectors, keyed by name."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        name = connector.metadata.name
        if name in self._connectors:
            raise ValueError(f"connector {name!r} is already registered")
        self._connectors[name] = connector

    def get(self, name: str) -> Connector:
        if name not in self._connectors:
            raise KeyError(f"unknown connector {name!r}")
        return self._connectors[name]

    def by_category(self, category: str) -> list[Connector]:
        return [c for c in self._connectors.values() if c.metadata.category == category]

    def all(self) -> list[Connector]:
        return list(self._connectors.values())

    def names(self) -> list[str]:
        return sorted(self._connectors)

    def clear(self) -> None:
        """Reset the registry (used by tests for isolation)."""
        self._connectors.clear()


#: Process-wide default registry.
registry = ConnectorRegistry()


def register(cls):
    """Class decorator: instantiate ``cls`` and add it to the default registry.

    Usage::

        @register
        class MyConnector(Connector):
            metadata = ConnectorMetadata(...)
            def fetch(self, req): ...
            def synthetic(self, req): ...
    """
    registry.register(cls())
    return cls
