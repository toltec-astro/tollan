"""Mixed projections share storage, not attribute readers or cell presence."""

from types import MappingProxyType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel

from tollan.accessor.pandas.model_table import ModelColumn, ModelTableAccessor


class Direct(BaseModel):
    value: int | None


class Stored(BaseModel):
    text: str | None


def column_maps():
    return {
        Direct: {
            "number": ModelColumn("value", dtype="Int64"),
            "direct_only": ModelColumn("absent", default=7, dtype="Int64"),
        },
        Stored: {"number": ModelColumn("text", converter=int, dtype=pd.Int64Dtype())},
    }


def test_mixed_projection_preserves_order_and_uses_each_reader_once():
    calls = []

    def convert(value):
        calls.append(value)
        return int(value)

    columns = column_maps()
    columns[Stored]["number"] = ModelColumn("text", converter=convert, dtype="Int64")
    models = [Stored(text="5"), Direct(value=2**60 + 1), Stored(text=None)]
    table = ModelTableAccessor.from_models(iter(models), columns=columns)
    assert table.number.iloc[:2].tolist() == [5, 2**60 + 1]
    assert pd.isna(table.number.iloc[2])
    assert calls == ["5"]
    assert table.direct_only.isna().tolist() == [True, False, True]
    assert table.direct_only.iloc[1] == 7
    assert table.dtypes.astype(str).tolist() == ["Int64", "Int64"]


def test_empty_input_retains_union_schema_and_empty_maps_retain_rows():
    columns = column_maps() | {SimpleNamespace: {"object": ModelColumn("value")}}
    table = ModelTableAccessor.from_models([], columns=columns)
    assert list(table) == ["number", "direct_only", "object"]
    assert table.dtypes.astype(str).tolist() == ["Int64", "Int64", "object"]
    table = ModelTableAccessor.from_models([object(), object()], columns={object: {}})
    assert table.shape == (2, 0)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Int64", "Float64"),
        (None, "Int64"),
        ("int64", "Int64"),
        (pd.CategoricalDtype(["a", "b"]), pd.CategoricalDtype(["a", "c"])),
    ],
)
def test_dtype_conflicts_fail_before_consuming_models(left, right):
    def models():
        pytest.fail("Consumed input before checking the complete schema")
        yield

    with pytest.raises(TypeError, match="number.*Direct.*Stored"):
        ModelTableAccessor.from_models(
            models(),
            columns={
                Direct: {"number": ModelColumn("value", dtype=left)},
                Stored: {"number": ModelColumn("text", dtype=right)},
            },
        )


def test_conflicting_unused_map_does_not_mutate_destination():
    table = pd.DataFrame({"number": pd.array([4], dtype="Int64")})
    before = table.copy()
    columns = column_maps()
    columns[Stored]["number"] = ModelColumn("text", dtype="string")
    with pytest.raises(TypeError, match="Conflicting dtypes"):
        ModelTableAccessor(table).update_from_models(
            [Direct(value=5)], columns=columns, inplace=True
        )
    pd.testing.assert_frame_equal(table, before)


def test_dispatch_requires_exact_type_without_subclass_fallback():
    class Child(Direct):
        pass

    with pytest.raises(TypeError, match="exact model type.*Child"):
        ModelTableAccessor.from_models([Child(value=1)], columns=column_maps())
    columns = column_maps() | {Child: {"number": ModelColumn("value", dtype="Int64")}}
    assert (
        ModelTableAccessor.from_models([Child(value=1)], columns=columns).number[0] == 1
    )


def test_plain_mapping_and_fallback_have_identical_projection_and_update_semantics():
    columns = {
        "number": ModelColumn("value", dtype="Int64"),
        "extra": ModelColumn("absent", default=None, dtype=object),
    }
    models = [Direct(value=2**60 + 1), SimpleNamespace(value=None)]
    plain = ModelTableAccessor.from_models(iter(models), columns=columns)
    fallback = ModelTableAccessor.from_models(iter(models), columns={None: columns})
    pd.testing.assert_frame_equal(plain, fallback)
    for mapping in ({}, columns):
        pd.testing.assert_frame_equal(
            ModelTableAccessor.from_models([], columns=mapping),
            ModelTableAccessor.from_models([], columns={None: mapping}),
        )
    table = pd.DataFrame(
        {"number": pd.array([4, 5, 6], dtype="Int64")}, index=[9, 9, 1]
    )
    updates = {2: models[0], 0: models[1]}
    accessor = ModelTableAccessor(table)
    pd.testing.assert_frame_equal(
        accessor.update_from_models(updates, columns=columns),
        accessor.update_from_models(updates, columns={None: columns}),
    )


def test_exact_projection_replaces_fallback_including_an_empty_projection():
    class Child(Direct):
        pass

    calls = []

    def read_fallback(value):
        calls.append(value)
        return value

    columns = {
        None: {
            "number": ModelColumn("value", dtype="Int64", converter=read_fallback),
            "fallback_only": ModelColumn("absent", default=8, dtype="Int64"),
        },
        Stored: {"number": ModelColumn("text", converter=int, dtype="Int64")},
        Direct: {},
    }
    models = [Stored(text="3"), Direct(value=4), Child(value=5)]
    table = ModelTableAccessor.from_models(models, columns=columns)
    assert calls == [5]
    expected = pd.DataFrame(
        {
            "number": pd.array([3, None, 5], dtype="Int64"),
            "fallback_only": pd.array([None, None, 8], dtype="Int64"),
        }
    )
    pd.testing.assert_frame_equal(table, expected)
    result = ModelTableAccessor(expected.fillna(9)).update_from_models(
        models, columns=columns
    )
    assert calls == [5, 5]
    assert result.number.tolist() == [3, 9, 5]
    assert result.fallback_only.tolist() == [9, 9, 8]


def test_unused_fallback_participates_in_schema_validation():
    def models():
        pytest.fail("Consumed input before checking fallback dtype")
        yield

    with pytest.raises(TypeError, match="number.*Direct.*None"):
        ModelTableAccessor.from_models(
            models(),
            columns={
                Direct: {"number": ModelColumn("value", dtype="Int64")},
                None: {"number": ModelColumn("value", dtype="Float64")},
            },
        )


@pytest.mark.parametrize("inplace", [False, True])
def test_updates_distinguish_unmapped_cells_from_projected_nulls(inplace):
    table = pd.DataFrame(
        {
            "number": pd.array([1, 2, 3, 4], dtype="Float64"),
            "direct_only": pd.array([10, 20, 30, 40], dtype="Int64"),
            "note": ["a", "b", "c", "d"],
        },
        index=[7, 2, 7, 2],
    )
    table.attrs["batch"] = "mixed"
    before = table.copy()
    columns = column_maps()
    columns[Direct]["added"] = ModelColumn("value", dtype="Int64")
    result = ModelTableAccessor(table).update_from_models(
        {-1: Stored(text=None), 0: Direct(value=5), 2: Stored(text="6")},
        columns=columns,
        inplace=inplace,
    )
    if inplace:
        assert result is None
        result = table
    else:
        pd.testing.assert_frame_equal(table, before)
    expected = before.copy()
    expected["number"] = pd.array([5, 2, 6, None], dtype="Float64")
    expected["direct_only"] = pd.array([7, 20, 30, 40], dtype="Int64")
    expected["added"] = pd.array([5, None, None, None], dtype="Int64")
    pd.testing.assert_frame_equal(result, expected)
    assert result.attrs == before.attrs


def test_full_sequence_and_positional_mapping_agree_with_unused_destinations():
    models = [Direct(value=3), Stored(text="4")]
    columns = column_maps() | {object: {"unused": ModelColumn("value", dtype="Int64")}}
    table = pd.DataFrame(index=[9, 9])
    accessor = ModelTableAccessor(table)
    result = accessor.update_from_models(iter(models), columns=columns)
    reversed_positions = accessor.update_from_models(
        {1: models[1], 0: models[0]}, columns=columns
    )
    expected = ModelTableAccessor.from_models(models, columns=columns)
    expected.index = table.index
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(reversed_positions, expected)


def test_object_columns_preserve_nested_values_and_normalize_default_dtype():
    payload = [1, {"key": 2}]
    table = ModelTableAccessor.from_models(
        [SimpleNamespace(value=payload), Direct(value=3)],
        columns={
            SimpleNamespace: {"payload": ModelColumn("value")},
            Direct: {"payload": ModelColumn("value", dtype=np.dtype(object))},
        },
    )
    assert table.payload[0] is payload
    assert table.payload[1] == 3
    assert table.payload.dtype == object


def test_read_only_mapping_containers_are_supported_without_mutation():
    columns = MappingProxyType(
        {kind: MappingProxyType(mapping) for kind, mapping in column_maps().items()}
    )
    table = ModelTableAccessor.from_models([Stored(text="5")], columns=columns)
    assert table.number.tolist() == [5]
    assert list(columns[Stored]) == ["number"]


@pytest.mark.parametrize(
    ("dtype", "value"),
    [
        (pd.CategoricalDtype(["a", "b"], ordered=True), "b"),
        ("uint64[pyarrow]", 2**63 + 1),
        ("datetime64[ns, UTC]", pd.Timestamp("2026-10-23", tz="UTC")),
    ],
)
def test_shared_extension_storage_preserves_values_and_nulls(dtype, value):
    class Wrapped(SimpleNamespace):
        pass

    models = [SimpleNamespace(value=value), Wrapped(data=None)]
    columns = {
        SimpleNamespace: {"value": ModelColumn("value", dtype=dtype)},
        Wrapped: {"value": ModelColumn("data", dtype=pd.api.types.pandas_dtype(dtype))},
    }
    table = ModelTableAccessor.from_models(models, columns=columns)
    expected = pd.DataFrame({"value": pd.array([value, None], dtype=dtype)})
    pd.testing.assert_frame_equal(table, expected)
    result = ModelTableAccessor(table).update_from_models(
        {1: models[0], 0: models[1]}, columns=columns
    )
    pd.testing.assert_frame_equal(result, expected.iloc[::-1].reset_index(drop=True))


def test_nonnullable_storage_is_kept_when_all_rows_map_and_rejected_otherwise():
    columns = {
        Direct: {"number": ModelColumn("value", dtype="int64")},
        Stored: {"number": ModelColumn("text", converter=int, dtype=np.int64)},
    }
    models = [Direct(value=3), Stored(text="4")]
    expected = ModelTableAccessor.from_models(models, columns=columns)
    result = ModelTableAccessor(pd.DataFrame(index=range(2))).update_from_models(
        {1: models[1], 0: models[0]}, columns=columns
    )
    pd.testing.assert_frame_equal(result, expected)
    assert result.number.dtype == np.dtype("int64")
    with pytest.raises((ValueError, TypeError)):
        ModelTableAccessor.from_models(models, columns=columns | {Stored: {}})


@pytest.mark.parametrize(
    "failure", ["unmapped_type", "missing_attribute", "lossy_value"]
)
def test_projection_errors_do_not_publish_partial_updates(failure):
    table = pd.DataFrame({"number": pd.array([1, 2], dtype="Int64")})
    before = table.copy()
    columns = column_maps()
    bad = SimpleNamespace(value=1.5)
    if failure != "unmapped_type":
        attr = "missing" if failure == "missing_attribute" else "value"
        columns[SimpleNamespace] = {"number": ModelColumn(attr, dtype="Int64")}
    with pytest.raises((TypeError, AttributeError)):
        ModelTableAccessor(table).update_from_models(
            [Direct(value=5), bad], columns=columns, inplace=True
        )
    pd.testing.assert_frame_equal(table, before)
