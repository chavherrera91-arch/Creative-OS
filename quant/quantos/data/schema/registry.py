"""Schema registry: versions, lookup and registered migrations.

The registry is the single authority on "what does dataset X look like at
version N" and on how to move a frame between versions. Evolution is always an
explicit, registered :class:`Migration` — never silent column drift (I8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from quantos.data.schema.base import Schema

__all__ = ["Migration", "SchemaRegistry", "schema_registry"]


@dataclass(frozen=True)
class Migration:
    """A registered, single-step schema migration.

    Attributes:
        schema_name: the dataset this migration belongs to.
        from_version: source schema version.
        to_version: target schema version (must be ``from_version + 1``).
        transform: pure function mapping a ``from_version`` frame to a
            ``to_version`` frame.
        description: what changed and why (lineage).
    """

    schema_name: str
    from_version: int
    to_version: int
    transform: Callable[[pd.DataFrame], pd.DataFrame]
    description: str = ""

    def __post_init__(self) -> None:
        if self.to_version != self.from_version + 1:
            raise ValueError("migrations must be single-step (to_version == from_version + 1)")


class SchemaRegistry:
    """Holds every (name, version) schema plus the migrations between them."""

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, int], Schema] = {}
        self._migrations: dict[tuple[str, int], Migration] = {}

    def register(self, schema: Schema) -> None:
        """Register a schema version (idempotent for an identical re-register).

        Raises:
            ValueError: if a *different* schema is already registered under the
                same (name, version) — versions are immutable once published.
        """
        key = (schema.name, schema.version)
        existing = self._schemas.get(key)
        if existing is not None and existing != schema:
            raise ValueError(f"schema {schema.name!r} v{schema.version} is already registered")
        self._schemas[key] = schema

    def get(self, name: str, version: int) -> Schema:
        """Fetch one exact schema version."""
        try:
            return self._schemas[(name, version)]
        except KeyError as exc:
            raise KeyError(f"no schema {name!r} v{version} registered") from exc

    def latest(self, name: str) -> Schema:
        """Fetch the highest registered version of a schema."""
        versions = [v for (n, v) in self._schemas if n == name]
        if not versions:
            raise KeyError(f"no schema named {name!r} registered")
        return self._schemas[(name, max(versions))]

    def names(self) -> list[str]:
        """All registered dataset names, sorted."""
        return sorted({n for (n, _v) in self._schemas})

    def add_migration(self, m: Migration) -> None:
        """Register a migration step; both endpoint versions must exist."""
        self.get(m.schema_name, m.from_version)
        self.get(m.schema_name, m.to_version)
        self._migrations[(m.schema_name, m.from_version)] = m

    def migrate(self, df: pd.DataFrame, name: str, from_v: int, to_v: int) -> pd.DataFrame:
        """Transform a frame across versions by chaining registered steps.

        Args:
            df: frame conforming to schema ``name`` at ``from_v``.
            name: dataset name.
            from_v: version the frame currently conforms to.
            to_v: target version (``>= from_v``; equal is a no-op copy).

        Returns:
            The frame transformed to ``to_v``.

        Raises:
            KeyError: when a required migration step is not registered.
            ValueError: when asked to migrate backwards.
        """
        if to_v < from_v:
            raise ValueError("downgrade migrations are not supported")
        out = df.copy()
        version = from_v
        while version < to_v:
            step = self._migrations.get((name, version))
            if step is None:
                raise KeyError(f"no migration registered for {name!r} v{version} -> v{version + 1}")
            out = step.transform(out)
            version = step.to_version
        return out

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (name -> registered versions)."""
        summary: dict[str, Any] = {}
        for name in self.names():
            versions = sorted(v for (n, v) in self._schemas if n == name)
            summary[name] = {"versions": versions, "latest": versions[-1]}
        return summary


#: Module-level singleton — connectors register their schemas here on import.
schema_registry = SchemaRegistry()
