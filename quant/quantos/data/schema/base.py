"""Schema primitives: :class:`FieldSpec` and versioned :class:`Schema`.

A ``Schema`` is the explicit, versioned contract for one dataset in the lake
(DATA_INFRASTRUCTURE §3.1). Every table carries a point-in-time key
(``time_column``, default ``event_time``) distinct from ``ingested_at`` so all
research reads can be as-of correct (invariant I2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["FieldSpec", "Schema", "SchemaVersion"]

#: A schema version is a plain monotonically increasing integer.
SchemaVersion = int


@dataclass(frozen=True)
class FieldSpec:
    """Specification of one column in a dataset.

    Attributes:
        name: column name.
        dtype: logical dtype — one of ``"float64" | "int64" | "string" |
            "bool" | "datetime"`` (datetimes are always tz-aware UTC, §4).
        nullable: whether nulls are legal; non-nullable nulls are dropped (or
            rejected) by the validator.
        description: human-readable meaning of the field.
        unit: optional unit, e.g. ``"USD"``, ``"bps"``.
        min: optional lower bound; values below raise a validation warning
            (and are clamped when coercing).
        max: optional upper bound, symmetric to ``min``.
    """

    name: str
    dtype: str
    nullable: bool = False
    description: str = ""
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
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
    """A named, versioned dataset contract.

    Attributes:
        name: dataset name, e.g. ``"market"``.
        version: integer version; evolution goes through ``Migration``s.
        fields: ordered column specifications.
        primary_key: columns that uniquely identify a row — always include
            ``symbol`` + ``event_time`` (or a natural id for news, §4).
        time_column: the point-in-time key used by as-of reads (I2).
    """

    name: str
    version: SchemaVersion
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...] = field(default=("symbol", "event_time"))
    time_column: str = "event_time"

    def __post_init__(self) -> None:
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"schema {self.name!r} v{self.version} has duplicate field names")
        for key in self.primary_key:
            if key not in names:
                raise ValueError(f"primary key column {key!r} is not a field of {self.name!r}")
        if self.time_column not in names:
            raise ValueError(f"time column {self.time_column!r} is not a field of {self.name!r}")
        if self.version < 1:
            raise ValueError("schema versions start at 1")

    @property
    def field_names(self) -> tuple[str, ...]:
        """Ordered column names."""
        return tuple(f.name for f in self.fields)

    def spec(self, name: str) -> FieldSpec:
        """Look up one field's specification by name."""
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"schema {self.name!r} v{self.version} has no field {name!r}")

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (pinned into lineage records, I8)."""
        return {
            "name": self.name,
            "version": self.version,
            "fields": [f.as_dict() for f in self.fields],
            "primary_key": list(self.primary_key),
            "time_column": self.time_column,
        }
