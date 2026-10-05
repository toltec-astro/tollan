"""Tests for lazy xarray reductions and retained metadata."""

from __future__ import annotations

import dask
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
    assert isinstance(median.data.data, da.Array)
    assert isinstance(mad.data.data, da.Array)
    assert median.data.compute().item() == 2.0
    assert mad.data.compute().item() == 1.4826
    assert median.data.u.unit is None


def test_reduction_defers_source_reads_and_shares_them_between_outputs() -> None:
    reads = []

    @dask.delayed
    def read():
        reads.append("read")
        return np.array([1.0, 2.0, 8.0])

    values = da.from_delayed(read(), shape=(3,), dtype=float)
    source = xr.DataArray(values, dims="sample", name="signal")
    median, mad = reduce_median_mad(source, dim="sample")
    assert reads == []
    result_median, result_mad = dask.compute(median, mad, scheduler="synchronous")
    assert reads == ["read"]
    assert result_median.signal.item() == 2.0
    assert result_mad.signal.item() == 1.4826


def test_missing_dimension_is_rejected_before_source_reads() -> None:
    @dask.delayed
    def unreadable():
        pytest.fail("Missing-dimension validation must not read the source.")

    values = da.from_delayed(unreadable(), shape=(3,), dtype=float)
    source = xr.DataArray(values, dims="sample")
    with pytest.raises(ValueError, match="No variables on dimension 'missing'"):
        reduce_median_mad(source, dim="missing")


@pytest.mark.parametrize("as_dataset", [False, True])
def test_empty_dimension_is_rejected_before_source_reads(*, as_dataset: bool) -> None:
    @dask.delayed
    def unreadable():
        pytest.fail("Empty-dimension validation must not read the source.")

    values = da.from_delayed(unreadable(), shape=(0,), dtype=float)
    source = xr.DataArray(values, dims="sample", name="signal")
    if as_dataset:
        source = source.to_dataset()
    with pytest.raises(ValueError, match="Cannot reduce empty dimension 'sample'"):
        reduce_median_mad(source, dim="sample")


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("retained_axis", [False, True])
@pytest.mark.parametrize("n_samples", [3, 4])
def test_mixed_dtypes_match_numpy_before_and_after_computing(
    *, chunked: bool, retained_axis: bool, n_samples: int
) -> None:
    values = np.array([[1.01, 2.03, 8.13, 10.07], [10.2, 14.3, 17.9, 20.1]])
    values = values[:, :n_samples] if retained_axis else values[0, :n_samples]
    dims = ("sensor", "sample") if retained_axis else ("sample",)
    source = xr.Dataset(
        {
            dtype: (dims, values.astype(dtype))
            for dtype in ["int16", "int64", "float32", "float64"]
        }
    )
    if chunked:
        source = source.chunk({"sample": 2})
    median, mad = reduce_median_mad(source, dim="sample")
    computed = dask.compute(median, mad)
    for name, data in source.data_vars.items():
        array = data.values
        center = np.median(array, axis=-1)
        scatter = np.median(abs(array - np.expand_dims(center, -1)), axis=-1) * 1.4826
        for lazy, actual, expected in zip(
            (median, mad), computed, (center, scatter), strict=True
        ):
            assert isinstance(lazy[name].data, da.Array)
            assert lazy[name].dtype == actual[name].dtype == expected.dtype
            np.testing.assert_array_equal(actual[name], expected)


def test_dataset_variables_keep_independent_units_and_shared_metadata() -> None:
    source = xr.Dataset(
        {
            "voltage": xr.DataArray([1.0, 2.0, 8.0], dims="sample").u.set(u.V),
            "temperature": xr.DataArray([10.0, 20.0, 80.0], dims="sample").u.set(u.K),
            "label": "observation",
        },
        coords={"sample": [0, 1, 2], "sensor": 42},
        attrs={"description": "measurement"},
    )
    median, mad = dask.compute(*reduce_median_mad(source, dim="sample"))
    for result in (median, mad):
        assert set(result.data_vars) == {"voltage", "temperature"}
        assert result.attrs == source.attrs
        xr.testing.assert_identical(result.sensor, source.sensor)
        assert "sample" not in result.coords
        assert result.voltage.u.unit == u.V
        assert result.temperature.u.unit == u.K
    assert median.voltage.item() == 2.0
    assert median.temperature.item() == 20.0
    assert mad.temperature.item() == pytest.approx(mad.voltage.item() * 10.0)
