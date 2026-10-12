"""Standalone pandas predicates and query namespace customization."""

from enum import Flag, IntFlag
from types import MappingProxyType

import pandas as pd
import pytest

from tollan.accessor.pandas.model_table import ModelTableAccessor
from tollan.utils.pandas import bits_all_set, bits_any_set, query


@pytest.mark.parametrize(
    ("predicate", "mask", "expected"),
    [
        (bits_any_set, 3, [False, True, True, True, pd.NA]),
        (bits_all_set, 3, [False, False, False, True, pd.NA]),
        (bits_any_set, 0, [False, False, False, False, pd.NA]),
        (bits_all_set, 0, [True, True, True, True, pd.NA]),
    ],
)
@pytest.mark.parametrize("use_enum_mask", [False, True])
def test_integer_predicates_preserve_nullable_masks(
    predicate, mask, expected, use_enum_mask
):
    values = pd.Series(
        [0, 1, 2, 3, None], dtype="Int64", index=[7, 7, 1, 2, 3], name="flags"
    )
    if use_enum_mask:
        flags = Flag("Flags", {"a": 1, "b": 2})
        mask = flags(mask)
    pd.testing.assert_series_equal(
        predicate(values, mask),
        pd.Series(expected, index=values.index, name="flags", dtype="boolean"),
    )


@pytest.mark.parametrize("enum_cls", [Flag, IntFlag])
@pytest.mark.parametrize(
    ("predicate", "mask", "expected"),
    [
        (bits_any_set, 3, [False, True, False, True, pd.NA]),
        (bits_all_set, 3, [False, False, False, True, pd.NA]),
        (bits_any_set, 0, [False, False, False, False, pd.NA]),
        (bits_all_set, 0, [True, True, False, True, pd.NA]),
    ],
)
def test_flag_predicates_keep_enum_identity(enum_cls, predicate, mask, expected):
    first = enum_cls("First", {"a": 1, "b": 2})
    second = enum_cls("Second", {"a": 1, "b": 2})
    values = pd.Series(
        [first(0), first.a, second.a, first(3), None],
        dtype=object,
        index=[7, 7, 1, 2, 3],
        name="flags",
    )
    pd.testing.assert_series_equal(
        predicate(values, first(mask)),
        pd.Series(expected, index=values.index, name="flags", dtype="boolean"),
    )
    with pytest.raises(TypeError, match="enum flag mask"):
        predicate(values, mask)


def _above(values, threshold):
    return values > threshold


@pytest.mark.parametrize("entrypoint", ["standalone", "accessor"])
def test_query_custom_namespace_is_not_mutated_and_columns_win(entrypoint):
    flags = Flag("Flags", {"a": 1, "b": 2})
    namespace = MappingProxyType({"Flags": flags, "limit": 30, "above": _above})
    table = pd.DataFrame(
        {
            "flags": pd.Series([flags.a, flags.b, flags(3), None], dtype=object),
            "exposure": [60, 30, 20, 0],
            "tags": [["science"], ["engineering"], [], None],
        }
    )
    table.index = [7, 7, 1, 2]
    table.attrs["note"] = "unchanged"
    before = table.copy(deep=True)

    class Queries(ModelTableAccessor):
        def _get_query_namespace(self):
            return namespace

    def select(expression):
        if entrypoint == "standalone":
            return query(table, expression, namespace=namespace)
        return Queries(table).query(expression)

    for _ in range(2):
        pd.testing.assert_frame_equal(
            select(
                'contains(tags, "science") & above(exposure, limit) '
                "& bits_any_set(flags, Flags.a | Flags.b)"
            ),
            table.iloc[[0]],
        )
    pd.testing.assert_frame_equal(table, before)
    assert dict(namespace) == {"Flags": flags, "limit": 30, "above": _above}
    table["limit"] = [100, 0, 0, 0]
    table["contains"] = [0, 1, 1, 0]
    pd.testing.assert_frame_equal(
        select("above(exposure, limit) & contains == 1"), table.iloc[[1, 2]]
    )


def test_custom_helper_override_is_local_to_query():
    table = pd.DataFrame({"tags": [["science"], [], None]})

    def nonempty(values, _value):
        return values.map(bool)

    namespace = {"contains": nonempty}
    assert query(
        table, 'contains(tags, "engineering")', namespace=namespace
    ).index.tolist() == [0]
    assert query(table, 'contains(tags, "engineering")').empty
    assert namespace == {"contains": nonempty}
