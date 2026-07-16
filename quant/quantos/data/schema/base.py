"""Schema primitives: field specifications and versioned dataset schemas.

A :class:`Schema` describes one dataset in the lake: its columns (as
:class:`FieldSpec`), its primary key and its point-in-time column
(``event_time`` by convention — invariant I2 depends on it). Schemas are
immutable; evolution happens by registering a *new version* plus a migration
(see :mod:`quantos.data.schema.registry`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    """One column of a dataset schema.

    ``dtype`` is a pandas dtype string (e.g. ``"float64"``, ``"int64"``,
    ``"string"``, ``"bool"``, ``"datetime64[ns, UTC]"``). ``min``/``max`` are
    optional sanity bounds enforced by the validator (out-of-range values are
    clamped with a warning, per the data-model conventions).
    """

    name: str
    dtype: str
    nullable: bool = False
    description: str = ""
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "description": self.description,
            "unit": self.unit,
            "min": self.min,
            "max": self.max,
        }


@dataclass(frozen=True)
class Schema:
    """A versioned dataset schema.

    ``primary_key`` columns identify a record (typically
    ``("symbol", "event_time")``); ``time_column`` is the point-in-time key
    used by as-of reads — it must always be tz-aware UTC and non-decreasing
    per symbol (the validator enforces this).
    """

    name: str
    version: int
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...]  # e.g. ("symbol", "event_time")
    time_column: str = "event_time"  # point-in-time key (I2)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"schema version must be >= 1, got {self.version}")
        names = self.field_names
        if len(set(names)) != len(names):
            raise ValueError(f"schema {self.name!r} has duplicate field names")
        for key in self.primary_key:
            if key not in names:
                raise ValueError(f"primary key column {key!r} not in schema fields")
        if self.time_column not in names:
            raise ValueError(f"time column {self.time_column!r} not in schema fields")

    # -- introspection ---------------------------------------------------------
    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def field(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"schema {self.name!r} v{self.version} has no field {name!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "fields": [f.as_dict() for f in self.fields],
            "primary_key": list(self.primary_key),
            "time_column": self.time_column,
        }
