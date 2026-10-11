"""Flag-valued query columns preserve each enum's identity."""

from enum import Flag, IntFlag

import pandas as pd
import pytest

from tollan.accessor.pandas.model_table import ModelTableAccessor


@pytest.mark.parametrize(
    ("expression", "positions"),
    [
        ("bits_any_set(data_kind, First.a | First.b)", [0, 2]),
        ("bits_all_set(data_kind, First.a | First.b)", [2]),
        ("bits_any_set(data_kind, First.a & ~First.b)", [0, 2]),
        ("bits_any_set(data_kind, First.a & First.b)", []),
        ("bits_all_set(data_kind, First.a & First.b)", [0, 2, 4]),
        ("~bits_any_set(data_kind, First.a)", [1, 4]),
    ],
)
def test_mixed_enum_bits(expression, positions):
    first = Flag("First", {"a": 1, "b": 2})
    second = Flag("Second", {"a": 1})

    class Queries(ModelTableAccessor):
        _query_namespace = ModelTableAccessor._query_namespace | {"First": first}

    table = pd.DataFrame(
        {
            "data_kind": pd.Series(
                [first.a, second.a, first.a | first.b, None, first(0)], dtype=object
            ),
        }
    )
    table.index = [7, 7, 1, 2, 4]
    pd.testing.assert_frame_equal(
        Queries(table).query(expression), table.iloc[positions]
    )
    with pytest.raises(TypeError, match="enum flag mask"):
        Queries(table).query("bits_any_set(data_kind, 1)")


@pytest.mark.parametrize("predicate", ["bits_any_set", "bits_all_set"])
def test_intflag_equal_values_keep_their_namespaces(predicate):
    first = IntFlag("First", {"a": 1})
    second = IntFlag("Second", {"a": 1})
    assert first.a == second.a

    class Queries(ModelTableAccessor):
        _query_namespace = ModelTableAccessor._query_namespace | {"First": first}

    table = pd.DataFrame({"value": pd.Series([first.a, second.a, None], dtype=object)})
    assert Queries(table).query(f"{predicate}(value, First.a)").index.tolist() == [0]
