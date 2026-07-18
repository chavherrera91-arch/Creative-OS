"""Shared base for channel connectors (derivatives, on-chain, macro, ...).

Concrete connectors implement one method — ``_canonical`` — producing the
full deterministic synthetic series for a symbol; windowing, mode handling
and the optional-live-backend protocol live here once. A real backend is
added by overriding ``_live_fetch`` with lazy imports and env-provided keys
only (no hardcoded credentials, I6).
"""

from __future__ import annotations

from abc import abstractmethod

import pandas as pd

from quantos.data.connectors._synthetic import slice_window
from quantos.data.connectors.base import Connector, FetchRequest, FetchResult
from quantos.data.schema.base import Schema

__all__ = ["ChannelConnector"]


class ChannelConnector(Connector):
    """Connector template: canonical synthetic series + optional live backend."""

    #: The registered schema this connector's rows conform to.
    schema: Schema

    @abstractmethod
    def _canonical(self, req: FetchRequest) -> pd.DataFrame:
        """Full deterministic series for ``req.symbol`` (pure function, I8).

        Must return schema-shaped rows over the canonical event-time grid;
        ``ingested_at`` should equal ``event_time`` so synthetic frames are
        fully reproducible (no wall clock).
        """

    def _live_fetch(self, req: FetchRequest) -> pd.DataFrame | None:
        """Hook for an optional real backend.

        Overrides must lazy-import their client and read credentials from the
        environment only. Return ``None`` when the backend is unavailable —
        never raise for a missing optional dependency (I6).
        """
        return None

    def synthetic(self, req: FetchRequest) -> FetchResult:
        """Deterministic offline rows for the requested window (I6, I8)."""
        return FetchResult(
            rows=slice_window(self._canonical(req), req),
            schema_version=self.schema.version,
            source_mode="synthetic",
        )

    def fetch(self, req: FetchRequest) -> FetchResult:
        """Fetch honouring ``req.mode``; labelled ``"live"`` only when real."""
        if req.mode == "synthetic":
            return self.synthetic(req)
        try:
            live_rows = self._live_fetch(req)
        except Exception:  # noqa: BLE001 — a failing backend degrades gracefully
            live_rows = None
        if live_rows is not None:
            return FetchResult(
                rows=slice_window(live_rows, req),
                schema_version=self.schema.version,
                source_mode="live",
            )
        if req.mode == "live":
            raise RuntimeError(
                f"connector {self.metadata.name!r} has no live backend available; "
                "use mode='auto' or 'synthetic' for the offline path (I6)"
            )
        return self.synthetic(req)
