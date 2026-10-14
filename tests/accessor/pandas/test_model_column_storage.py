"""Mapped values must fit numeric storage without implicit value changes."""

from functools import partial
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel

from tollan.accessor.pandas.model_table import (
    ExplicitColumnRule,
    ModelColumn,
    ModelColumnMapper,
    ModelTableAccessor,
)


def project(values, dtype, **kwargs):
    return ModelTableAccessor.from_models(
        [SimpleNamespace(value=value) for value in values],
        columns={"number": ModelColumn("value", dtype=dtype, **kwargs)},
    )["number"]


@pytest.mark.parametrize("dtype", ["int64", "Int64", "int64[pyarrow]"])
def test_integer_storage_rejects_fractional_values(dtype):
    with pytest.raises(TypeError):
        project([1.5], dtype)
    assert project([1.0, 3], dtype).tolist() == [1, 3]
    assert project([1.5], dtype, converter=round).tolist() == [2]


def test_numeric_text_requires_explicit_conversion():
    with pytest.raises(TypeError, match="exactly"):
        project(["3"], "int64")
    assert project(["3"], "int64", converter=int).tolist() == [3]


@pytest.mark.parametrize("dtype", ["int8", "Int8", "int8[pyarrow]"])
@pytest.mark.parametrize("value", [-129, 128, np.int64(128)])
def test_integer_storage_rejects_overflow(dtype, value):
    with pytest.raises((OverflowError, TypeError, ValueError)):
        project([value], dtype)


@pytest.mark.parametrize("dtype", ["uint64", "UInt64", "uint64[pyarrow]"])
def test_unsigned_storage_checks_sign_and_preserves_large_integers(dtype):
    assert int(project([2**64 - 1], dtype).iloc[0]) == 2**64 - 1
    with pytest.raises((OverflowError, TypeError, ValueError)):
        project([-1], dtype)


@pytest.mark.parametrize("dtype", ["float64", "Float64", "float64[pyarrow]"])
@pytest.mark.parametrize("value_type", [int, np.int64, np.uint64])
def test_float_storage_does_not_round_large_integers(dtype, value_type):
    with pytest.raises((TypeError, ValueError)):
        project([value_type(2**60 + 1)], dtype)
    assert project([value_type(2**50)], dtype).iloc[0] == float(2**50)


@pytest.mark.parametrize("dtype", ["float32", "Float32", "float32[pyarrow]"])
@pytest.mark.parametrize("value", [1.1, 1e300, 1e-300])
def test_float_storage_rejects_precision_loss_overflow_and_underflow(dtype, value):
    with pytest.raises(TypeError, match="exactly"):
        project([value], dtype)


@pytest.mark.parametrize("dtype", [np.longdouble, np.clongdouble, "complex64"])
def test_numpy_extended_and_complex_storage_cannot_hide_precision_loss(dtype):
    with pytest.raises(TypeError, match="exactly"):
        project([2**200 + 1], dtype)
    assert project([2], dtype).iloc[0] == 2


def test_complex_storage_checks_both_components():
    assert project([1.5 + 2j], "complex64").iloc[0] == 1.5 + 2j
    with pytest.raises(TypeError, match="exactly"):
        project([1.5 + 1.1j], "complex64")


def test_explicit_float_conversion_owns_precision_and_runs_once():
    calls = []

    def convert(value):
        calls.append(value)
        return np.float32(value)

    result = project([1.1, None], "Float32", converter=convert)
    assert calls == [1.1]
    assert result.iloc[0] == np.float32(1.1)
    assert pd.isna(result.iloc[1])


@pytest.mark.parametrize("dtype", ["Int64", "int64[pyarrow]"])
def test_nulls_defaults_and_empty_columns(dtype):
    result = project([None, pd.NA, np.nan, 2**60 + 1], dtype)
    assert result.isna().tolist() == [True, True, True, False]
    assert int(result.iloc[-1]) == 2**60 + 1
    assert project([], dtype).dtype == pd.api.types.pandas_dtype(dtype)
    with pytest.raises(TypeError):
        ModelTableAccessor.from_models(
            [object()], columns={"value": ModelColumn("absent", 1.5, dtype)}
        )


@pytest.mark.parametrize("dtype", ["bool", "boolean", "bool[pyarrow]"])
def test_boolean_storage_does_not_turn_arbitrary_values_into_true(dtype):
    with pytest.raises((TypeError, ValueError)):
        project([2], dtype)
    assert project([True, False], dtype).tolist() == [True, False]


@pytest.mark.parametrize("value", [None, np.nan])
def test_nonnullable_boolean_storage_does_not_replace_nulls(value):
    with pytest.raises(TypeError, match="exactly"):
        project([value], "bool")


@pytest.mark.parametrize("dtype", ["float64", "Float64", "float64[pyarrow]"])
def test_nan_and_infinity_are_preserved(dtype):
    result = project([np.nan, np.inf, -np.inf, -0.0], dtype)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1:3].tolist() == [np.inf, -np.inf]
    assert np.signbit(result.iloc[-1])


def test_preparation_failure_precedes_any_inplace_update():
    table = pd.DataFrame({"first": [1], "second": [2]})
    before = table.copy()
    with pytest.raises(TypeError, match="second"):
        ModelTableAccessor(table).update_from_models(
            [SimpleNamespace(a=3, b=1.5)],
            columns={
                "first": ModelColumn("a", dtype="int64"),
                "second": ModelColumn("b", dtype="int64"),
            },
            inplace=True,
        )
    pd.testing.assert_frame_equal(table, before)


class Reading(BaseModel):
    label: str
    value: float


def make_mapper(column, **kwargs):
    return ModelColumnMapper(
        name_rules=[("value", "number")],
        type_rules=[ExplicitColumnRule(columns={"value": column})],
        **kwargs,
    )


def test_mapper_checks_actual_attribute_not_matched_field():
    with pytest.raises(TypeError, match="label.*numeric dtype"):
        make_mapper(ModelColumn("label", dtype="Int64"))(Reading)
    columns = make_mapper(ModelColumn("value", dtype="Int64"))(Reading)
    assert (
        ModelTableAccessor.from_models(
            [Reading(label="x", value=1)], columns=columns
        ).iloc[0, 0]
        == 1
    )


def test_mapper_checks_converter_output_instead_of_input_annotation():
    def convert(value: str) -> int:
        return len(value)

    columns = make_mapper(ModelColumn("label", dtype="Int64", converter=convert))(
        Reading
    )
    assert (
        ModelTableAccessor.from_models(
            [Reading(label="abc", value=0)], columns=columns
        ).iloc[0, 0]
        == 3
    )

    def invalid(value: float, *, prefix: str) -> str:
        return f"{prefix}{value}"

    with pytest.raises(TypeError, match="numeric dtype"):
        make_mapper(
            ModelColumn("value", dtype="Int64", converter=partial(invalid, prefix="v"))
        )(Reading)


def test_annotations_do_not_replace_runtime_storage_check():
    def convert(value: float) -> int:
        return round(value)

    columns = make_mapper(ModelColumn("value", dtype="int8", converter=convert))(
        Reading
    )
    with pytest.raises((OverflowError, TypeError)):
        ModelTableAccessor.from_models([Reading(label="x", value=128)], columns=columns)


def test_mapper_checks_callable_instance_return_annotation():
    class Convert:
        prefix: str

        def __call__(self, value: float) -> str:
            return str(value)

    with pytest.raises(TypeError, match="numeric dtype"):
        make_mapper(ModelColumn("value", dtype="int64", converter=Convert()))(Reading)


def test_unknown_annotations_and_duck_paths_still_get_checked():
    def convert(value: Any) -> Any:
        return value

    columns = make_mapper(
        ModelColumn("reading.value", dtype="int64", converter=convert)
    )(Reading)
    with pytest.raises(TypeError, match="exactly"):
        ModelTableAccessor.from_models(
            [SimpleNamespace(reading=SimpleNamespace(value=1.5))], columns=columns
        )
