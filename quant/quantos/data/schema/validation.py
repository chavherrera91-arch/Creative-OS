"""Data validation against a :class:`Schema` (DATA_INFRASTRUCTURE §3.2).

``DataValidator.validate`` checks required columns, dtypes (coercing when
asked), non-null on non-nullable fields, primary-key uniqueness, a monotonic
non-decreasing time column (per symbol, I2) and min/max ranges. It returns a
cleaned frame plus an accurate :class:`ValidationReport` — bad data never
reaches the curated tier silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quantos.data.schema.base import FieldSpec, Schema

__all__ = ["DataValidator", "ValidationReport"]


@dataclass
class ValidationReport:
    """Outcome of validating one frame against one schema.

    Attributes:
        ok: True when no error was raised (warnings alone do not fail).
        errors: fatal problems — the frame must not be written when non-empty.
        warnings: repaired or tolerable problems (dropped dupes, clamps...).
        rows: rows in the cleaned frame.
        dropped: rows removed while cleaning (nulls, duplicate keys).
    """

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rows: int = 0
    dropped: int = 0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (I4)."""
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "rows": self.rows,
            "dropped": self.dropped,
        }


def _coerce_column(series: pd.Series, spec: FieldSpec) -> pd.Series:
    """Coerce one column toward its declared logical dtype."""
    if spec.dtype == "float64":
        return pd.to_numeric(series, errors="coerce").astype("float64")
    if spec.dtype == "int64":
        return pd.to_numeric(series, errors="coerce").astype("Int64")
    if spec.dtype == "datetime":
        return pd.to_datetime(series, errors="coerce", utc=True)
    if spec.dtype == "bool":
        return series.astype(bool)
    if spec.dtype == "string":
        return series.astype("string")
    raise ValueError(f"unknown dtype {spec.dtype!r} for field {spec.name!r}")


def _conforms(series: pd.Series, spec: FieldSpec) -> bool:
    """True when a column's storage dtype already matches its logical dtype."""
    kind = series.dtype.kind
    if spec.dtype == "float64":
        return kind == "f"
    if spec.dtype == "int64":
        return kind == "i" or str(series.dtype) == "Int64"
    if spec.dtype == "datetime":
        return kind == "M"
    if spec.dtype == "bool":
        return kind == "b"
    if spec.dtype == "string":
        return kind in ("O", "U") or str(series.dtype) == "string"
    return False


class DataValidator:
    """Validates (and optionally repairs) frames against a schema."""

    def validate(
        self, df: pd.DataFrame, schema: Schema, *, coerce: bool = True
    ) -> tuple[pd.DataFrame, ValidationReport]:
        """Validate a frame against a schema.

        Args:
            df: candidate frame.
            schema: the contract to validate against.
            coerce: when True, repair what can honestly be repaired (coerce
                dtypes, drop null/duplicate rows, sort time, clamp ranges) and
                record it as warnings; when False, every such problem is an
                error and the frame is rejected untouched.

        Returns:
            ``(cleaned_frame, report)``. When ``report.ok`` is False the frame
            must not be written to the curated tier.
        """
        report = ValidationReport(ok=True)
        original_rows = len(df)

        missing = [name for name in schema.field_names if name not in df.columns]
        if missing:
            report.ok = False
            report.errors.append(f"missing required columns: {missing}")
            report.rows = original_rows
            return df, report

        extras = [c for c in df.columns if c not in schema.field_names]
        if extras:
            report.warnings.append(f"ignoring undeclared columns: {extras}")
        out = df[list(schema.field_names)].copy()

        # Dtypes -------------------------------------------------------------
        for spec in schema.fields:
            if _conforms(out[spec.name], spec):
                continue
            if coerce:
                out[spec.name] = _coerce_column(out[spec.name], spec)
                report.warnings.append(f"coerced column {spec.name!r} to {spec.dtype}")
            else:
                report.ok = False
                report.errors.append(
                    f"column {spec.name!r} has dtype {out[spec.name].dtype}, "
                    f"expected {spec.dtype}"
                )

        # Non-null on non-nullable ------------------------------------------
        for spec in schema.fields:
            if spec.nullable:
                continue
            nulls = out[spec.name].isna()
            if nulls.any():
                if coerce:
                    out = out.loc[~nulls]
                    report.warnings.append(
                        f"dropped {int(nulls.sum())} rows with null {spec.name!r}"
                    )
                else:
                    report.ok = False
                    report.errors.append(
                        f"column {spec.name!r} has {int(nulls.sum())} nulls but is non-nullable"
                    )

        # Primary-key uniqueness --------------------------------------------
        dupes = out.duplicated(subset=list(schema.primary_key), keep="last")
        if dupes.any():
            if coerce:
                out = out.loc[~dupes]
                report.warnings.append(
                    f"dropped {int(dupes.sum())} duplicate primary-key rows (kept last)"
                )
            else:
                report.ok = False
                report.errors.append(
                    f"{int(dupes.sum())} duplicate rows on primary key {schema.primary_key}"
                )

        # Monotonic non-decreasing time column, per symbol (I2, §4) ----------
        sort_keys = (
            ["symbol", schema.time_column] if "symbol" in out.columns else [schema.time_column]
        )
        grouped = (
            out.groupby("symbol", sort=False)[schema.time_column]
            if "symbol" in out.columns
            else [(None, out[schema.time_column])]
        )
        monotonic = all(series.is_monotonic_increasing for _, series in grouped)
        if not monotonic:
            if coerce:
                out = out.sort_values(sort_keys, kind="stable")
                report.warnings.append(f"sorted rows by {sort_keys} (time was non-monotonic)")
            else:
                report.ok = False
                report.errors.append(
                    f"time column {schema.time_column!r} is not non-decreasing per symbol"
                )

        # Ranges -------------------------------------------------------------
        for spec in schema.fields:
            if spec.min is None and spec.max is None:
                continue
            values = pd.to_numeric(out[spec.name], errors="coerce")
            below = values < spec.min if spec.min is not None else pd.Series(False, index=out.index)
            above = values > spec.max if spec.max is not None else pd.Series(False, index=out.index)
            n_out = int((below | above).sum())
            if n_out:
                report.warnings.append(
                    f"{n_out} values of {spec.name!r} outside [{spec.min}, {spec.max}]"
                    + (" (clamped)" if coerce else "")
                )
                if coerce:
                    out[spec.name] = values.clip(lower=spec.min, upper=spec.max)

        report.rows = len(out)
        report.dropped = original_rows - len(out)
        if not report.ok:
            return df, report
        return out.reset_index(drop=True), report
