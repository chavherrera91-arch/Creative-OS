"""Data catalog: what the lake holds, under which schema, how fresh.

One queryable inventory over the curated tier: dataset → schema + version,
row counts, symbols, event-time coverage and lineage back to the producing
connector. This is the map of the platform's primary asset.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantos.data.connectors.registry import ConnectorRegistry
from quantos.data.connectors.registry import registry as default_registry
from quantos.data.schema.registry import SchemaRegistry
from quantos.data.schema.registry import schema_registry as default_schema_registry
from quantos.data.store.base import Store

__all__ = ["DataCatalog"]


class DataCatalog:
    """Inventory of every curated dataset in a store."""

    def __init__(
        self,
        store: Store,
        schemas: SchemaRegistry | None = None,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self.store = store
        self.schemas = schemas or default_schema_registry
        self.registry = registry or default_registry

    def _describe(self, table: str) -> dict[str, Any]:
        frame = self.store.read("curated", table)
        entry: dict[str, Any] = {
            "dataset": table,
            "rows": len(frame),
            "symbols": sorted(frame["symbol"].unique()) if "symbol" in frame.columns else [],
        }
        try:
            schema = self.schemas.latest(table)
            entry["schema"] = schema.name
            entry["schema_version"] = schema.version
            time_col = schema.time_column
        except KeyError:
            entry["schema"] = None
            entry["schema_version"] = None
            time_col = "event_time"
        if time_col in frame.columns and len(frame):
            entry["first_event_time"] = str(pd.Timestamp(frame[time_col].min()))
            entry["last_event_time"] = str(pd.Timestamp(frame[time_col].max()))
        else:
            entry["first_event_time"] = None
            entry["last_event_time"] = None
        try:  # lineage: which connector produces this dataset
            meta = self.registry.get(table).metadata
            entry["connector"] = meta.name
            entry["category"] = meta.category
            entry["cadence_seconds"] = meta.cadence_seconds
        except KeyError:
            entry["connector"] = None
            entry["category"] = None
            entry["cadence_seconds"] = None
        return entry

    def datasets(self) -> list[dict[str, Any]]:
        """Describe every curated dataset (operational tables excluded)."""
        return [
            self._describe(table)
            for table in self.store.tables("curated")
            if not table.startswith("_")
        ]

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable catalog (I4)."""
        return {"datasets": self.datasets(), "schemas": self.schemas.as_dict()}
