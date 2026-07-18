"""Versioned, validated schemas — the contract every dataset honours (M2).

Every dataset in the lake has an explicit :class:`Schema` with a version;
data is validated against it on write and schema evolution goes through
registered :class:`Migration` steps — never silent column drift (I8).
"""

from quantos.data.schema.base import FieldSpec, Schema, SchemaVersion
from quantos.data.schema.registry import Migration, SchemaRegistry, schema_registry
from quantos.data.schema.validation import DataValidator, ValidationReport

__all__ = [
    "DataValidator",
    "FieldSpec",
    "Migration",
    "Schema",
    "SchemaRegistry",
    "SchemaVersion",
    "ValidationReport",
    "schema_registry",
]
