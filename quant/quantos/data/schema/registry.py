"""Schema registry and migrations.

The :class:`SchemaRegistry` holds every version of every dataset schema and
the :class:`Migration` steps between consecutive versions. ``migrate`` walks
the migration chain so a frame written under an old schema version can always
be brought up to the latest — schema evolution is explicit, never silent.

A module-level ``schema_registry`` singleton is the default registry that
connectors register their schemas into (mirroring the connector registry).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from quantos.data.schema.base import Schema


@dataclass(frozen=True)
class Migration:
    """A single-step transform from one schema version to the next.

    ``transform`` receives a frame valid under ``from_version`` and must
    return a frame valid under ``to_version``. Multi-version upgrades are
    composed by the registry, one step at a time.
    """

    schema_name: str
    from_version: int
    to_version: int
    transform: Callable[[pd.DataFrame], pd.DataFrame]
    description: str = ""

    def __post_init__(self) -> None:
        if self.to_version != self.from_version + 1:
            raise ValueError(
                "migrations must step one version at a time "
                f"({self.from_version} -> {self.to_version})"
            )


class SchemaRegistry:
    """Versioned schema store with explicit migrations."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[int, Schema]] = {}
        self._migrations: dict[tuple[str, int], Migration] = {}

    # -- schemas ---------------------------------------------------------------
    def register(self, schema: Schema) -> None:
        versions = self._schemas.setdefault(schema.name, {})
        if schema.version in versions:
            raise ValueError(
                f"schema {schema.name!r} v{schema.version} is already registered"
            )
        versions[schema.version] = schema

    def latest(self, name: str) -> Schema:
        versions = self._versions_of(name)
        return versions[max(versions)]

    def get(self, name: str, version: int) -> Schema:
        versions = self._versions_of(name)
        if version not in versions:
            raise KeyError(f"schema {name!r} has no version {version}")
        return versions[version]

    def versions(self, name: str) -> list[int]:
        return sorted(self._versions_of(name))

    def names(self) -> list[str]:
        return sorted(self._schemas)

    # -- migrations --------------------------------------------------------------
    def add_migration(self, m: Migration) -> None:
        key = (m.schema_name, m.from_version)
        if key in self._migrations:
            raise ValueError(
                f"migration {m.schema_name!r} v{m.from_version}->v{m.to_version} "
                "is already registered"
            )
        self._migrations[key] = m

    def migrate(
        self, df: pd.DataFrame, name: str, from_v: int, to_v: int
    ) -> pd.DataFrame:
        """Upgrade ``df`` from schema version ``from_v`` to ``to_v``.

        Applies each registered single-step migration in order. Raises
        ``KeyError`` if any step in the chain is missing.
        """
        if to_v < from_v:
            raise ValueError(f"cannot migrate downwards ({from_v} -> {to_v})")
        out = df.copy()
        for v in range(from_v, to_v):
            step = self._migrations.get((name, v))
            if step is None:
                raise KeyError(f"no migration registered for {name!r} v{v}->v{v + 1}")
            out = step.transform(out)
        return out

    # -- internals -----------------------------------------------------------------
    def _versions_of(self, name: str) -> dict[int, Schema]:
        if name not in self._schemas:
            raise KeyError(f"unknown schema {name!r}")
        return self._schemas[name]


#: Default process-wide registry; connectors register their schemas here.
schema_registry = SchemaRegistry()
