"""Tests for lazy xarray reductions and retained metadata."""

from __future__ import annotations

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from astropy import units as u

from tollan.utils.xarray import reduce_median_mad


def test_reduction_accepts_selected_and_normalized_values() -> None:
    values = np.array([[1, 2, 3], [2, 8, 6], [10, 20, 30]], dtype=float)
    measurements = xr.Dataset(
        {
            "voltage": (("sensor", "sample"), da.from_array(values, chunks=(1, 2))),
            "reference": ("sample", [1.0, 1.0, 1.0]),
        },
        coords={"sensor": [10, 20, 30], "sample": [0.0, 10.0, 20.0]},
    )
    selected = measurements.isel(sensor=[0, 1])
    normalized = selected.assign(
        voltage=selected.voltage / xr.DataArray([1.0, 2.0], dims="sensor")
    )
    normalized.voltage.attrs["units"] = ""
    median, mad = reduce_median_mad(normalized, dim="sensor")
    assert list(median) == ["voltage"]
    assert median.voltage.dims == ("sample",)
    np.testing.assert_allclose(median.voltage.compute(), [1, 3, 3])
    np.testing.assert_allclose(mad.voltage.compute(), np.array([0, 1, 0]) * 1.4826)
    assert mad.voltage.attrs["units"] == ""
    np.testing.assert_array_equal(measurements.voltage, values)
    with pytest.raises(ValueError, match="No variables on dimension 'missing'"):
        reduce_median_mad(measurements, dim="missing")


@pytest.mark.parametrize("dim", ["row", "sample"])
def test_reduce_median_mad_retains_units_coordinates_and_nan_behavior(dim: str) -> None:
    values = np.array([[1.0, 2.0, np.nan], [2.0, 4.0, 8.0], [3.0, 6.0, 9.0]])
    source = xr.DataArray(
        da.from_array(values, chunks=(1, 2)),
        dims=("row", "sample"),
        coords={"row": [10, 20, 30], "sample": [0, 1, 2]},
        name="signal",
        attrs={"description": "measurement"},
    ).u.set(u.mV)
    before = source.copy(deep=False)
    median, mad = reduce_median_mad(source, dim=dim)
    axis = source.get_axis_num(dim)
    expected_median = np.median(values, axis=axis)
    expected_mad = (
        np.median(abs(values - np.expand_dims(expected_median, axis=axis)), axis=axis)
        * 1.4826
    )
    for reduced, expected in [(median, expected_median), (mad, expected_mad)]:
        assert isinstance(reduced.signal.data, da.Array)
        np.testing.assert_allclose(reduced.signal.compute(), expected)
        assert reduced.signal.attrs == source.attrs
        assert dim not in reduced.dims
        for retained in reduced.dims:
            xr.testing.assert_identical(reduced[retained], source[retained])
    xr.testing.assert_identical(source, before)


def test_reduce_median_mad_unnamed_dataarray_uses_standard_variable_name() -> None:
    source = xr.DataArray([1.0, 2.0, 8.0], dims="sample")
    median, mad = reduce_median_mad(source, dim="sample")
    assert list(median) == list(mad) == ["data"]
    assert median.data.compute().item() == 2.0
    assert mad.data.compute().item() == 1.4826
    assert median.data.u.unit is None
