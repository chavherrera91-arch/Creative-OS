"""WP-2.1 — versioned schema system: registry, migrations, validation."""

from __future__ import annotations

import pandas as pd
import pytest

from quantos.data.schema import (
    DataValidator,
    FieldSpec,
    Migration,
    Schema,
    SchemaRegistry,
)

V1 = Schema(
    name="demo",
    version=1,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime"),
        FieldSpec("close", "float64", min=0.0),
    ),
    primary_key=("symbol", "event_time"),
)

V2 = Schema(
    name="demo",
    version=2,
    fields=(
        FieldSpec("symbol", "string"),
        FieldSpec("event_time", "datetime"),
        FieldSpec("close", "float64", min=0.0),
        FieldSpec("volume", "float64", nullable=True),
    ),
    primary_key=("symbol", "event_time"),
)


def make_frame(n: int = 4) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": ["BTC/USDT"] * n,
            "event_time": times,
            "close": [100.0 + i for i in range(n)],
        }
    )


class TestSchema:
    def test_schema_validates_its_own_shape(self) -> None:
        with pytest.raises(ValueError):
            Schema(
                name="bad",
                version=1,
                fields=(FieldSpec("close", "float64"),),
                primary_key=("symbol",),  # not a field
                time_column="close",
            )
        with pytest.raises(ValueError):
            Schema(
                name="bad",
                version=1,
                fields=(FieldSpec("event_time", "datetime"),),
                primary_key=("event_time",),
                time_column="missing",
            )

    def test_spec_lookup_and_as_dict(self) -> None:
        assert V1.spec("close").min == 0.0
        payload = V1.as_dict()
        assert payload["version"] == 1
        assert payload["primary_key"] == ["symbol", "event_time"]


class TestRegistry:
    def test_register_latest_get(self) -> None:
        reg = SchemaRegistry()
        reg.register(V1)
        reg.register(V2)
        assert reg.get("demo", 1) is V1
        assert reg.latest("demo") is V2
        assert reg.names() == ["demo"]

    def test_conflicting_reregister_rejected(self) -> None:
        reg = SchemaRegistry()
        reg.register(V1)
        reg.register(V1)  # identical re-register is idempotent
        conflicting = Schema(
            name="demo",
            version=1,
            fields=(FieldSpec("symbol", "string"), FieldSpec("event_time", "datetime")),
            primary_key=("symbol", "event_time"),
        )
        with pytest.raises(ValueError):
            reg.register(conflicting)

    def test_migration_transforms_v1_frame_to_v2(self) -> None:
        reg = SchemaRegistry()
        reg.register(V1)
        reg.register(V2)
        reg.add_migration(
            Migration(
                schema_name="demo",
                from_version=1,
                to_version=2,
                transform=lambda df: df.assign(volume=0.0),
                description="add volume with a neutral default",
            )
        )
        migrated = reg.migrate(make_frame(), "demo", 1, 2)
        assert "volume" in migrated.columns
        cleaned, report = DataValidator().validate(migrated, V2)
        assert report.ok
        assert list(cleaned.columns) == list(V2.field_names)

    def test_missing_migration_step_raises(self) -> None:
        reg = SchemaRegistry()
        reg.register(V1)
        reg.register(V2)
        with pytest.raises(KeyError):
            reg.migrate(make_frame(), "demo", 1, 2)


class TestValidator:
    def test_valid_frame_passes(self) -> None:
        cleaned, report = DataValidator().validate(make_frame(), V1)
        assert report.ok and not report.errors
        assert report.rows == 4 and report.dropped == 0
        assert cleaned["close"].dtype.kind == "f"

    def test_missing_required_column_rejected(self) -> None:
        bad = make_frame().drop(columns=["close"])
        _, report = DataValidator().validate(bad, V1)
        assert not report.ok
        assert any("missing required columns" in e for e in report.errors)

    def test_duplicate_primary_key_rejected_without_coerce(self) -> None:
        frame = pd.concat([make_frame(), make_frame().tail(1)], ignore_index=True)
        _, report = DataValidator().validate(frame, V1, coerce=False)
        assert not report.ok
        assert any("primary key" in e for e in report.errors)

    def test_duplicate_primary_key_deduped_with_coerce(self) -> None:
        frame = pd.concat([make_frame(), make_frame().tail(2)], ignore_index=True)
        cleaned, report = DataValidator().validate(frame, V1)
        assert report.ok
        assert report.rows == 4 and report.dropped == 2
        assert not cleaned.duplicated(subset=["symbol", "event_time"]).any()

    def test_non_monotonic_time_rejected_without_coerce(self) -> None:
        frame = make_frame().iloc[::-1].reset_index(drop=True)
        _, report = DataValidator().validate(frame, V1, coerce=False)
        assert not report.ok
        assert any("non-decreasing" in e for e in report.errors)

    def test_non_monotonic_time_sorted_with_coerce(self) -> None:
        frame = make_frame().iloc[::-1].reset_index(drop=True)
        cleaned, report = DataValidator().validate(frame, V1)
        assert report.ok
        assert cleaned["event_time"].is_monotonic_increasing

    def test_nulls_on_non_nullable_dropped_and_counted(self) -> None:
        frame = make_frame()
        frame.loc[1, "close"] = None
        cleaned, report = DataValidator().validate(frame, V1)
        assert report.ok
        assert report.rows == 3 and report.dropped == 1
        assert not cleaned["close"].isna().any()

    def test_range_violation_clamped_with_warning(self) -> None:
        frame = make_frame()
        frame.loc[0, "close"] = -5.0
        cleaned, report = DataValidator().validate(frame, V1)
        assert report.ok
        assert any("outside" in w for w in report.warnings)
        assert float(cleaned["close"].min()) >= 0.0

    def test_dtype_coercion_from_strings(self) -> None:
        frame = make_frame()
        frame["close"] = frame["close"].astype(str)
        cleaned, report = DataValidator().validate(frame, V1)
        assert report.ok
        assert cleaned["close"].dtype.kind == "f"
        _, strict = DataValidator().validate(frame, V1, coerce=False)
        assert not strict.ok
