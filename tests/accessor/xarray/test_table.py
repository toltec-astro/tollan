"""Unit-aware columnar projections and lazy positional row selection."""

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from astropy import units as u
from dask import delayed

from tollan.accessor.xarray import dataset_to_qtable, select_table_rows


@pytest.fixture
def dataset():
    return xr.Dataset(
        {
            "group": ("row", np.array([0, 0, 1, 1], dtype="int16")),
            "distance": ("row", np.arange(4.0), {"units": "km"}),
            "valid": ("row", [True, False, True, True]),
            "label": ("row", ["a", "b", "c", "d"]),
        },
        coords={"row": [10, 20, 30, 40]},
        attrs={"observer": "example"},
    )


def test_projection_preserves_columns_units_and_metadata(dataset):
    table = dataset_to_qtable(dataset, dim="row")
    assert table.colnames == list(dataset.data_vars)
    assert table.meta == dataset.attrs
    assert table["group"].dtype == np.dtype("int16")
    assert table["valid"].dtype == np.dtype(bool)
    assert table["label"].tolist() == ["a", "b", "c", "d"]
    np.testing.assert_array_equal(
        table["distance"].to_value(u.m), [0, 1000, 2000, 3000]
    )
    table.meta["observer"] = "changed"
    assert dataset.attrs["observer"] == "example"


def test_independently_editable_projection_preserves_source(dataset):
    before = dataset.copy(deep=True)
    table = dataset_to_qtable(dataset, dim="row", copy=True)
    table["group"][0] = 9
    table["distance"][0] = 5 * u.km
    table["valid"][0] = False
    assert table["group"][0] == 9
    assert table["distance"][0] == 5 * u.km
    assert not table["valid"][0]
    xr.testing.assert_identical(dataset, before)


def test_explicit_columns_include_coordinates_and_rename(dataset):
    table = dataset_to_qtable(
        xr.DataTree(dataset=dataset),
        dim="row",
        columns={"id": "row", "length": "distance"},
    )
    assert table.colnames == ["id", "length"]
    assert table["id"].tolist() == [10, 20, 30, 40]
    assert table["length"].unit == u.km


def test_dataarray_projection(dataset):
    table = dataset_to_qtable(dataset["distance"], dim="row")
    assert table.colnames == ["distance"]
    assert table["distance"].unit == u.km


@pytest.mark.parametrize("dims", [(), ("other",), ("row", "other")])
def test_projection_rejects_noncolumnar_values(dataset, dims):
    shape = tuple(4 if dim == "row" else 2 for dim in dims)
    dataset["bad"] = xr.DataArray(np.ones(shape), dims=dims)
    with pytest.raises(ValueError, match="Table column 'bad'"):
        dataset_to_qtable(dataset, dim="row")


def test_projection_rejects_missing_dimension_and_columns(dataset):
    with pytest.raises(KeyError, match="missing"):
        dataset_to_qtable(dataset, dim="missing")
    with pytest.raises(KeyError, match="missing"):
        dataset_to_qtable(dataset, dim="row", columns={"missing": "missing"})
    bare_dim = xr.Dataset({"value": ("row", [1, 2])})
    with pytest.raises(KeyError, match="row"):
        dataset_to_qtable(bare_dim, dim="row", columns={"id": "row"})


def test_invalid_units_are_not_silently_dropped(dataset):
    dataset["distance"].attrs["units"] = "invalid_unit"
    with pytest.raises(ValueError, match="invalid_unit"):
        dataset_to_qtable(dataset, dim="row")


@pytest.mark.parametrize("indices", [[1, 2], [0, 2], [], [0, 1, 2, 3]])
def test_selection_retains_original_row_order_and_units(dataset, indices):
    mask = xr.DataArray(np.isin(np.arange(4), indices), dims="row")
    selected = select_table_rows(xr.DataTree(dataset=dataset), mask, dim="row")
    xr.testing.assert_identical(selected, dataset.isel(row=indices))
    table = dataset_to_qtable(selected, dim="row")
    assert len(table) == len(indices)
    assert table["distance"].unit == u.km


def test_mask_is_positional_without_coordinate_alignment(dataset):
    mask = xr.DataArray(
        [True, False, False, False], dims="row", coords={"row": [40, 30, 20, 10]}
    )
    selected = select_table_rows(dataset, mask, dim="row")
    assert selected["row"].values.tolist() == [10]


@pytest.mark.parametrize(
    "mask",
    [
        xr.DataArray([True], dims="row"),
        xr.DataArray([True] * 4, dims="other"),
        xr.DataArray([1, 0, 0, 1], dims="row"),
        xr.DataArray(np.ones((4, 1), dtype=bool), dims=("row", "other")),
    ],
)
def test_invalid_masks_raise(dataset, mask):
    with pytest.raises(ValueError, match="boolean mask"):
        select_table_rows(dataset, mask, dim="row")


def test_lazy_selection_and_projection_only_read_requested_payload():
    reads = []

    @delayed
    def load(name, values):
        reads.append(name)
        return np.asarray(values)

    source = xr.Dataset(
        {
            "key": ("row", da.from_delayed(load("key", [0, 1]), (2,), int)),
            "value": (
                "row",
                da.concatenate(
                    [
                        da.from_delayed(load("first", [10.0]), (1,), float),
                        da.from_delayed(load("second", [20.0]), (1,), float),
                    ]
                ),
                {"units": "Hz"},
            ),
            "unused": ("row", da.from_delayed(load("unused", [3, 4]), (2,), int)),
        }
    )
    selected = select_table_rows(source, source["key"] == 1, dim="row")
    assert reads == ["key"]
    assert isinstance(selected["value"].data, da.Array)
    table = dataset_to_qtable(selected, dim="row", columns={"frequency": "value"})
    assert reads == ["key", "second"]
    assert table["frequency"].to_value(u.Hz).tolist() == [20.0]
