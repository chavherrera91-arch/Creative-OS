import pandas as pd
import pytest

from quantos.data.schema import (
    DataValidator,
    FieldSpec,
    Migration,
    Schema,
    SchemaRegistry,
)


def _mkt_v1() -> Schema:
    return Schema(
        name="mkt",
        version=1,
        fields=(
            FieldSpec("symbol", "string"),
            FieldSpec("event_time", "datetime64[ns, UTC]"),
            FieldSpec("close", "float64", min=0.0),
        ),
        primary_key=("symbol", "event_time"),
    )


def _frame(times, close, symbol="BTC"):
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(times),
            "event_time": pd.to_datetime(times, utc=True),
            "close": close,
        }
    )


# -- Schema ------------------------------------------------------------------

def test_schema_rejects_bad_version():
    with pytest.raises(ValueError):
        Schema("x", 0, (FieldSpec("event_time", "datetime64[ns, UTC]"),),
               primary_key=("event_time",))


def test_schema_rejects_pk_not_in_fields():
    with pytest.raises(ValueError):
        Schema("x", 1, (FieldSpec("event_time", "datetime64[ns, UTC]"),),
               primary_key=("missing",))


def test_schema_rejects_duplicate_fields():
    with pytest.raises(ValueError):
        Schema("x", 1,
               (FieldSpec("event_time", "datetime64[ns, UTC]"),
                FieldSpec("event_time", "datetime64[ns, UTC]")),
               primary_key=("event_time",))


# -- Registry + migrations ---------------------------------------------------

def test_registry_register_latest_get():
    reg = SchemaRegistry()
    reg.register(_mkt_v1())
    assert reg.latest("mkt").version == 1
    assert reg.get("mkt", 1).name == "mkt"
    assert reg.versions("mkt") == [1]
    assert "mkt" in reg.names()


def test_registry_duplicate_version_raises():
    reg = SchemaRegistry()
    reg.register(_mkt_v1())
    with pytest.raises(ValueError):
        reg.register(_mkt_v1())


def test_migration_must_step_one_version():
    with pytest.raises(ValueError):
        Migration("mkt", 1, 3, lambda d: d)


def test_migrate_applies_chain():
    reg = SchemaRegistry()
    v1 = _mkt_v1()
    v2 = Schema("mkt", 2, v1.fields + (FieldSpec("volume", "float64", nullable=True),),
                primary_key=("symbol", "event_time"))
    reg.register(v1)
    reg.register(v2)
    reg.add_migration(Migration("mkt", 1, 2, lambda d: d.assign(volume=0.0)))
    df = _frame(["2024-01-01", "2024-01-02"], [10.0, 11.0])
    out = reg.migrate(df, "mkt", 1, 2)
    assert "volume" in out.columns


def test_migrate_missing_step_raises():
    reg = SchemaRegistry()
    reg.register(_mkt_v1())
    with pytest.raises(KeyError):
        reg.migrate(_frame(["2024-01-01"], [1.0]), "mkt", 1, 2)


# -- Validator ---------------------------------------------------------------

def test_validator_accepts_clean_frame():
    clean, rep = DataValidator().validate(
        _frame(["2024-01-01", "2024-01-02"], [10.0, 11.0]), _mkt_v1()
    )
    assert rep.ok
    assert rep.rows == 2
    assert rep.dropped == 0


def test_validator_missing_required_column_is_error():
    df = pd.DataFrame({"symbol": ["BTC"], "close": [1.0]})  # no event_time
    _, rep = DataValidator().validate(df, _mkt_v1())
    assert not rep.ok
    assert any("event_time" in e for e in rep.errors)


def test_validator_rejects_duplicate_primary_keys():
    df = _frame(["2024-01-01", "2024-01-01"], [1.0, 2.0])
    _, rep = DataValidator().validate(df, _mkt_v1())
    assert not rep.ok
    assert any("duplicate primary-key" in e for e in rep.errors)


def test_validator_rejects_non_monotonic_time():
    df = _frame(["2024-01-02", "2024-01-01"], [1.0, 2.0])
    _, rep = DataValidator().validate(df, _mkt_v1())
    assert not rep.ok
    assert any("non-decreasing" in e for e in rep.errors)


def test_validator_clamps_out_of_range():
    clean, rep = DataValidator().validate(
        _frame(["2024-01-01", "2024-01-02"], [10.0, -5.0]), _mkt_v1()
    )
    assert rep.ok  # clamping is a warning, not an error
    assert clean["close"].min() >= 0.0
    assert any("outside" in w for w in rep.warnings)


def test_validator_drops_nulls_in_non_nullable():
    df = _frame(["2024-01-01", "2024-01-02"], [10.0, None])
    clean, rep = DataValidator().validate(df, _mkt_v1())
    assert rep.rows == 1
    assert rep.dropped == 1


def test_validator_rejects_tz_naive_time_without_coercion():
    df = pd.DataFrame({
        "symbol": ["BTC", "BTC"],
        "event_time": pd.to_datetime(["2024-01-01", "2024-01-02"]),  # tz-naive
        "close": [1.0, 2.0],
    })
    _, rep = DataValidator().validate(df, _mkt_v1(), coerce=False)
    assert not rep.ok
    assert any("event_time" in e and "dtype" in e for e in rep.errors)


def test_validator_coerces_tz_naive_time_to_utc():
    df = pd.DataFrame({
        "symbol": ["BTC", "BTC"],
        "event_time": pd.to_datetime(["2024-01-01", "2024-01-02"]),  # tz-naive
        "close": [1.0, 2.0],
    })
    clean, rep = DataValidator().validate(df, _mkt_v1(), coerce=True)
    assert rep.ok
    assert clean["event_time"].dt.tz is not None


def test_validator_drops_extra_columns_with_warning():
    df = _frame(["2024-01-01"], [1.0])
    df["junk"] = 1
    clean, rep = DataValidator().validate(df, _mkt_v1())
    assert "junk" not in clean.columns
    assert any("junk" in w for w in rep.warnings)
