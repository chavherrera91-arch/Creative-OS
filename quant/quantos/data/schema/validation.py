"""Schema validation: enforce a :class:`Schema` on a frame before it is stored.

The validator checks required columns, coerces dtypes, drops rows that violate
non-null constraints, enforces primary-key uniqueness and a monotonic
non-decreasing time column (per symbol), and clamps out-of-range values. It
returns a *cleaned* frame plus an accurate :class:`ValidationReport` — errors
mean the input violated the schema (``ok`` is False); the cleaned frame is
still repaired best-effort so callers can decide what to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.data.schema.base import Schema


@dataclass
class ValidationReport:
    """Outcome of validating one frame against one schema version."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rows: int = 0  # rows in the cleaned frame
    dropped: int = 0  # input rows removed (nulls, duplicate PKs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "rows": self.rows,
            "dropped": self.dropped,
        }


def _is_datetime_dtype(dtype: str) -> bool:
    return dtype.startswith("datetime64")


class DataValidator:
    """Validates and cleans a frame against a :class:`Schema`."""

    def validate(
        self, df: pd.DataFrame, schema: Schema, *, coerce: bool = True
    ) -> tuple[pd.DataFrame, ValidationReport]:
        """Return ``(cleaned_frame, report)``.

        Checks, in order: required columns → dtype coercion → non-null on
        non-nullable columns → primary-key uniqueness → monotonic
        non-decreasing ``time_column`` (per symbol when present) → min/max
        range (clamped with a warning when ``coerce``).
        """
        errors: list[str] = []
        warnings: list[str] = []
        out = df.copy()
        n_input = len(out)

        # 1) Required columns.
        for spec in schema.fields:
            if spec.name in out.columns:
                continue
            if spec.nullable and coerce:
                out[spec.name] = None
                warnings.append(f"nullable column {spec.name!r} missing; filled null")
            else:
                errors.append(f"missing required column {spec.name!r}")
        missing = [f.name for f in schema.fields if f.name not in out.columns]
        if missing:
            # Cannot meaningfully clean without the schema's columns.
            report = ValidationReport(False, errors, warnings, len(out), 0)
            return out, report

        # Extra columns are not part of the contract — drop with a warning.
        extras = [c for c in out.columns if c not in schema.field_names]
        if extras:
            warnings.append(f"dropped columns not in schema: {extras}")
            out = out.drop(columns=extras)
        out = out[list(schema.field_names)]

        # 2) Dtypes (coerce when asked; failed coercions become null).
        for spec in schema.fields:
            col = out[spec.name]
            if str(col.dtype) == spec.dtype:
                continue
            if not coerce:
                errors.append(
                    f"column {spec.name!r} has dtype {col.dtype}, expected {spec.dtype}"
                )
                continue
            try:
                if _is_datetime_dtype(spec.dtype):
                    out[spec.name] = pd.to_datetime(col, utc=True, errors="coerce")
                elif spec.dtype in ("float64", "float32", "int64", "int32"):
                    coerced = pd.to_numeric(col, errors="coerce")
                    out[spec.name] = coerced.astype(spec.dtype, errors="ignore")
                else:
                    out[spec.name] = col.astype(spec.dtype)
            except (TypeError, ValueError):
                errors.append(f"cannot coerce column {spec.name!r} to {spec.dtype}")

        # 3) Non-null on non-nullable columns (violating rows are dropped).
        required = [f.name for f in schema.fields if not f.nullable]
        null_mask = out[required].isna().any(axis=1)
        n_null = int(null_mask.sum())
        if n_null:
            warnings.append(f"dropped {n_null} row(s) with nulls in non-nullable columns")
            out = out[~null_mask]

        # 4) Primary-key uniqueness (duplicates are an error; keep the last).
        pk = list(schema.primary_key)
        dup_mask = out.duplicated(subset=pk, keep="last")
        n_dup = int(dup_mask.sum())
        if n_dup:
            errors.append(f"{n_dup} duplicate primary-key row(s) on {pk}")
            out = out[~dup_mask]

        # 5) Monotonic non-decreasing time column, per symbol when present.
        tcol = schema.time_column
        if pd.api.types.is_datetime64_any_dtype(out[tcol]):
            if out[tcol].dt.tz is None:
                errors.append(f"time column {tcol!r} is not tz-aware UTC")
            groups = out.groupby("symbol")[tcol] if "symbol" in out.columns else [(None, out[tcol])]
            for key, series in groups:
                if not series.is_monotonic_increasing:
                    label = f" for symbol {key!r}" if key is not None else ""
                    errors.append(f"time column {tcol!r} is not non-decreasing{label}")
            sort_by = (["symbol", tcol] if "symbol" in out.columns else [tcol])
            out = out.sort_values(sort_by, kind="stable")
        else:
            errors.append(f"time column {tcol!r} is not a datetime column")

        # 6) Min/max range (clamp with a warning when coercing).
        for spec in schema.fields:
            if spec.min is None and spec.max is None:
                continue
            col = out[spec.name]
            if not pd.api.types.is_numeric_dtype(col):
                continue
            below = int((col < spec.min).sum()) if spec.min is not None else 0
            above = int((col > spec.max).sum()) if spec.max is not None else 0
            if below or above:
                warnings.append(
                    f"column {spec.name!r}: {below + above} value(s) outside "
                    f"[{spec.min}, {spec.max}]" + (" (clamped)" if coerce else "")
                )
                if coerce:
                    out[spec.name] = col.clip(lower=spec.min, upper=spec.max)

        out = out.reset_index(drop=True)
        report = ValidationReport(
            ok=not errors,
            errors=errors,
            warnings=warnings,
            rows=len(out),
            dropped=n_input - len(out),
        )
        return out, report
