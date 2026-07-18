"""Resilient, idempotent, resumable ingestion (M2).

``IngestionRunner`` drives every connector through the same pipeline:
circuit-breaker gate → fetch under a retry policy → validate → write raw +
upsert curated → advance watermark → record health. Re-running never
duplicates; a crash resumes from the last watermark.
"""

from quantos.data.ingest.retry import CircuitBreaker, RetryPolicy
from quantos.data.ingest.runner import IngestionRunner
from quantos.data.ingest.watermark import WatermarkStore

__all__ = [
    "CircuitBreaker",
    "IngestionRunner",
    "RetryPolicy",
    "WatermarkStore",
]
