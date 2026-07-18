"""Connector registry — self-registration, zero core edits (I7).

Adding a data source is exactly one new module: a ``Connector`` subclass
decorated with :func:`register`. The decorator instantiates and registers it
into the module-level :data:`registry`; the ``DataLake`` and scheduler
discover it there. No ``if source == "x"`` branching exists anywhere in the
core, and no core file references a specific connector.
"""

from __future__ import annotations

from typing import TypeVar

from quantos.data.connectors.base import Connector

__all__ = ["ConnectorRegistry", "register", "registry"]

C = TypeVar("C", bound=type[Connector])


class ConnectorRegistry:
    """Holds every registered connector instance, keyed by name."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        """Register (or replace) a connector under its metadata name."""
        self._connectors[connector.metadata.name] = connector

    def unregister(self, name: str) -> None:
        """Remove a connector; missing names are ignored (test hygiene)."""
        self._connectors.pop(name, None)

    def get(self, name: str) -> Connector:
        """Look up one connector by name."""
        try:
            return self._connectors[name]
        except KeyError as exc:
            raise KeyError(
                f"no connector named {name!r}; registered: {self.names()}"
            ) from exc

    def by_category(self, category: str) -> list[Connector]:
        """All connectors in a category, name-ordered (deterministic, I8)."""
        return [
            c
            for _, c in sorted(self._connectors.items())
            if c.metadata.category == category
        ]

    def all(self) -> list[Connector]:
        """Every registered connector, name-ordered (deterministic, I8)."""
        return [c for _, c in sorted(self._connectors.items())]

    def names(self) -> list[str]:
        """Sorted registered names."""
        return sorted(self._connectors)


#: Module-level singleton the whole platform discovers connectors through.
registry = ConnectorRegistry()


def register(cls: C) -> C:
    """Class decorator: instantiate and self-register a connector.

    Usage::

        @register
        class MyConnector(Connector):
            metadata = ConnectorMetadata(...)
    """
    registry.register(cls())
    return cls
