"""Exact element membership in collection-valued table cells."""

import numpy as np
import pandas as pd
import pytest

from tollan.accessor.pandas.model_table import ModelTableAccessor
from tollan.utils.pandas import contains, query


@pytest.fixture(params=["standalone", "accessor"])
def query_table(request):
    if request.param == "standalone":
        return query

    def query_with_accessor(table, expression):
        return ModelTableAccessor(table).query(expression)

    return query_with_accessor


@pytest.mark.parametrize("collection", [list, tuple, set, frozenset, np.asarray])
def test_contains_compares_elements_not_substrings_or_patterns(collection, query_table):
    table = pd.DataFrame(
        {
            "tags": [
                collection(["alpha", "beta"]),
                collection(["alphabet"]),
                collection(["a.*"]),
                collection(["ALPHA"]),
                collection([]),
            ]
        },
        index=pd.Index([7, 7, 2, 1, 1], name="row"),
    )
    before = table.copy(deep=True)
    pd.testing.assert_frame_equal(
        query_table(table, 'contains(tags, "alpha")'), table.iloc[[0]]
    )
    pd.testing.assert_frame_equal(
        query_table(table, 'contains(tags, "a.*")'), table.iloc[[2]]
    )
    pd.testing.assert_frame_equal(table, before)


@pytest.mark.parametrize("collection", [list, np.asarray])
@pytest.mark.parametrize(
    ("expression", "positions"),
    [
        ('contains(tags, "science")', [0, 1]),
        ('contains(tags, "science") and exposure > 30', [0]),
        ('contains(tags, "science") & bits_any_set(flags, 2)', [1]),
        ('contains(tags, "science") | contains(tags, "engineering")', [0, 1, 2]),
        ('~contains(tags, "science")', [2, 3, 4, 5, 6]),
        ('not contains(tags, "science")', [2, 3, 4, 5, 6]),
    ],
)
def test_contains_combines_with_queries_and_missing_cells(
    expression, positions, collection, query_table
):
    table = pd.DataFrame(
        {
            "tags": [
                collection(["science"]),
                collection(["science", "reviewed"]),
                collection(["engineering"]),
                collection([]),
                None,
                pd.NA,
                np.nan,
            ],
            "exposure": pd.array([60, 30, 10, None, None, None, None], dtype="Int64"),
            "flags": pd.array([1, 2, 0, None, None, None, None], dtype="Int64"),
        }
    )
    table.index = ["same", "same", "other", "empty", "null", "null", "null"]
    pd.testing.assert_frame_equal(query_table(table, expression), table.iloc[positions])


@pytest.mark.parametrize("values", [[], [None, pd.NA, np.nan]])
def test_contains_empty_and_all_missing_columns(values, query_table):
    table = pd.DataFrame({"tags": pd.Series(values, dtype=object)})
    pd.testing.assert_frame_equal(
        query_table(table, 'contains(tags, "a")'), table.iloc[:0]
    )
    pd.testing.assert_frame_equal(query_table(table, '~contains(tags, "a")'), table)


@pytest.mark.parametrize("invalid", ["science", b"science", 1, {"science": True}])
def test_contains_rejects_noncollection_cells(invalid, query_table):
    table = pd.DataFrame({"tags": [["science"], invalid]})
    with pytest.raises(
        TypeError, match="requires list, tuple, set, frozenset or ndarray cells"
    ):
        query_table(table, 'contains(tags, "science")')


def test_contains_reads_current_cells_without_caching(query_table):
    table = pd.DataFrame({"tags": [["alpha"], ["beta"]], "contains": [0, 1]})
    assert query_table(table, "contains == 1").index.tolist() == [1]
    table = table.drop(columns="contains")
    assert query_table(table, 'contains(tags, "alpha")').index.tolist() == [0]
    table.tags.iloc[1].append("alpha")
    assert query_table(table, 'contains(tags, "alpha")').index.tolist() == [0, 1]


def test_contains_returns_a_mask_for_direct_selection():
    values = pd.Series(
        [["alpha"], ("beta",), set(), None, pd.NA, np.nan],
        index=[7, 7, 1, 1, 2, 3],
        name="tags",
    )
    pd.testing.assert_series_equal(
        contains(values, "alpha"),
        pd.Series(
            [True, False, False, False, False, False], index=values.index, name="tags"
        ),
    )
