"""Versioned, validated dataset schemas for the Data Lake.

Every dataset has an explicit :class:`Schema` (columns, dtypes, primary key,
point-in-time column). Schemas are versioned in a :class:`SchemaRegistry` and
evolve only through registered :class:`Migration`\\ s — never silent column
drift. The :class:`DataValidator` enforces a schema on write.
"""

from quantos.data.schema.base import FieldSpec, Schema
from quantos.data.schema.registry import Migration, SchemaRegistry, schema_registry
from quantos.data.schema.validation import DataValidator, ValidationReport

__all__ = [
    "FieldSpec",
    "Schema",
    "Migration",
    "SchemaRegistry",
    "schema_registry",
    "DataValidator",
    "ValidationReport",
]
