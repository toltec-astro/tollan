"""Tests for xarray mapper implementation."""

from __future__ import annotations

from dataclasses import dataclass

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from astropy import units as u
from dask import delayed

from tollan.accessor.schema import Mapping, NameMapping, Schema
from tollan.accessor.xarray import XarrayMapper


@dataclass
class SourceSchema(Schema):
    """Schema shared by the xarray source-contract tests."""

    signal: Mapping = NameMapping("signal")
    sample: Mapping = NameMapping("sample")
    meta: Mapping = NameMapping("meta")
    child_only: Mapping = NameMapping("child_only")


class SourceMapper(XarrayMapper[SourceSchema]):
    """Mapper shared by the xarray source-contract tests."""


class TestXarrayMapper:
    """Test XarrayMapper for xarray.Dataset."""

    def test_from_dataset(self):
        """Create mapper from xarray Dataset."""
        ds = xr.Dataset(
            {
                "temp": (["x"], [25.0, 26.0]),
                "pressure": (["x"], [101.3, 101.4]),
            },
        )

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            pressure: Mapping = NameMapping("pressure")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        assert isinstance(mapper, XarrayMapper)

    def test_read_data_variable(self):
        """Read data variable values as numpy array."""
        ds = xr.Dataset({"temp": (["x"], [25.0, 26.0, 27.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_value(ds, mapper.schema.temp)

        # XarrayMapper returns .values (numpy array), not DataArray
        assert isinstance(value, np.ndarray)
        assert len(value) == 3
        assert value[0] == 25.0

    def test_read_coordinate(self):
        """Read coordinate values as numpy array."""
        ds = xr.Dataset({"data": (["time"], [1, 2])}, coords={"time": [0.0, 1.0]})

        @dataclass
        class TestSchema(Schema):
            time: Mapping = NameMapping("time")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_value(ds, mapper.schema.time)

        # XarrayMapper returns .values (numpy array), not DataArray
        assert isinstance(value, np.ndarray)
        assert len(value) == 2

    def test_read_attrs(self):
        """Read values from Dataset.attrs."""
        ds = xr.Dataset({"data": (["x"], [1, 2])})
        ds.attrs["metadata_field"] = "metadata_value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = NameMapping("metadata_field")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_value(ds, mapper.schema.meta)

        assert value == "metadata_value"

    def test_missing_field(self):
        """Missing field raises KeyError."""
        ds = xr.Dataset({"temp": (["x"], [25.0])})

        @dataclass
        class TestSchema(Schema):
            pressure: Mapping = NameMapping("pressure")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(ds, mapper.schema.pressure)

    def test_has_arr(self):
        """Test has_arr checks for data variables and coordinates."""
        ds = xr.Dataset(
            {"temp": (["x"], [25.0, 26.0])},
            coords={"x": [0, 1]},
        )
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            x: Mapping = NameMapping("x")
            meta: Mapping = NameMapping("meta")
            missing: Mapping = NameMapping("missing")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Both data vars and coords should return True
        assert mapper.has_arr(ds, mapper.schema.temp)
        assert mapper.has_arr(ds, mapper.schema.x)
        # Attributes should return False
        assert not mapper.has_arr(ds, mapper.schema.meta)
        # Missing fields should return False
        assert not mapper.has_arr(ds, mapper.schema.missing)

    def test_has_attr(self):
        """Test has_attr checks for attributes only."""
        ds = xr.Dataset(
            {"temp": (["x"], [25.0, 26.0])},
            coords={"x": [0, 1]},
        )
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            x: Mapping = NameMapping("x")
            meta: Mapping = NameMapping("meta")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # meta is an attribute
        assert mapper.has_attr(ds, mapper.schema.meta)
        # temp is a data variable, not an attribute
        assert not mapper.has_attr(ds, mapper.schema.temp)
        # x is a coordinate, not an attribute
        assert not mapper.has_attr(ds, mapper.schema.x)

    def test_get_arr_with_data_variable(self):
        """Test get_arr retrieves DataArray for data variable."""
        ds = xr.Dataset({"temp": (["x"], [25.0, 26.0, 27.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        arr = mapper.get_arr(ds, mapper.schema.temp)

        assert isinstance(arr, xr.DataArray)
        assert len(arr) == 3
        assert arr.values[0] == 25.0

    def test_get_arr_with_coordinate(self):
        """Test get_arr retrieves DataArray for coordinate."""
        ds = xr.Dataset(
            {"data": (["x"], [1, 2, 3])},
            coords={"x": [0.0, 1.0, 2.0]},
        )

        @dataclass
        class TestSchema(Schema):
            x: Mapping = NameMapping("x")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        arr = mapper.get_arr(ds, mapper.schema.x)

        assert isinstance(arr, xr.DataArray)
        assert len(arr) == 3
        assert arr.values[0] == 0.0

    def test_get_arr_with_attribute_fails(self):
        """Test get_arr raises error for attribute."""
        ds = xr.Dataset({"data": (["x"], [1, 2])})
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = NameMapping("meta")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="not found as an array in Dataset"):
            mapper.get_arr(ds, mapper.schema.meta)

    def test_get_arr_from_dataarray_with_coordinate(self):
        """Test get_arr retrieves coordinate from DataArray."""
        ds = xr.Dataset(
            {"temp": (["x", "y"], [[1, 2], [3, 4]])},
            coords={"x": [0.0, 1.0], "y": [10.0, 20.0]},
        )

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            x: Mapping = NameMapping("x")
            y: Mapping = NameMapping("y")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Get DataArray from Dataset
        temp_da = mapper.get_arr(ds, mapper.schema.temp)
        assert isinstance(temp_da, xr.DataArray)

        # Now get coordinates from the DataArray itself
        x_from_da = mapper.get_arr(temp_da, mapper.schema.x)
        assert isinstance(x_from_da, xr.DataArray)
        assert len(x_from_da) == 2
        assert x_from_da.values[0] == 0.0
        assert x_from_da.values[1] == 1.0

        y_from_da = mapper.get_arr(temp_da, mapper.schema.y)
        assert isinstance(y_from_da, xr.DataArray)
        assert len(y_from_da) == 2
        assert y_from_da.values[0] == 10.0
        assert y_from_da.values[1] == 20.0

    def test_get_arr_from_dataarray_fails_for_nonexistent_coord(self):
        """Test get_arr raises error for non-existent coordinate in DataArray."""
        ds = xr.Dataset(
            {"temp": (["x"], [1, 2, 3])},
            coords={"x": [0.0, 1.0, 2.0]},
        )

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            z: Mapping = NameMapping("z")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        temp_da = mapper.get_arr(ds, mapper.schema.temp)

        # Should fail when trying to get non-existent coordinate from DataArray
        with pytest.raises(ValueError, match="not found as an array in DataArray"):
            mapper.get_arr(temp_da, mapper.schema.z)

    def test_get_arr_dataset_vs_dataarray_coordinate_access(self):
        """Test get_arr works consistently for coords from Dataset vs DataArray."""
        ds = xr.Dataset(
            {"data": (["chan", "freq"], [[1, 2, 3], [4, 5, 6]])},
            coords={
                "chan": [0, 1],
                "freq": [1.0e9, 2.0e9, 3.0e9],
            },
        )

        @dataclass
        class TestSchema(Schema):
            data: Mapping = NameMapping("data")
            chan: Mapping = NameMapping("chan")
            freq: Mapping = NameMapping("freq")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Get coordinate from Dataset
        chan_from_ds = mapper.get_arr(ds, mapper.schema.chan)
        freq_from_ds = mapper.get_arr(ds, mapper.schema.freq)

        # Get DataArray, then get coordinates from it
        data_da = mapper.get_arr(ds, mapper.schema.data)
        chan_from_da = mapper.get_arr(data_da, mapper.schema.chan)
        freq_from_da = mapper.get_arr(data_da, mapper.schema.freq)

        # Both access methods should return equivalent arrays
        assert isinstance(chan_from_ds, xr.DataArray)
        assert isinstance(chan_from_da, xr.DataArray)
        assert (chan_from_ds.values == chan_from_da.values).all()

        assert isinstance(freq_from_ds, xr.DataArray)
        assert isinstance(freq_from_da, xr.DataArray)
        assert (freq_from_ds.values == freq_from_da.values).all()

    def test_get_scalar_from_attrs(self):
        """Test get_scalar retrieves scalar from attributes."""
        ds = xr.Dataset({"data": (["x"], [1, 2])})
        ds.attrs["obs_id"] = 12345

        @dataclass
        class TestSchema(Schema):
            obs_id: Mapping = NameMapping("obs_id")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_scalar(ds, mapper.schema.obs_id)

        assert value == 12345

    def test_get_scalar_from_0d_array(self):
        """Test get_scalar retrieves scalar from 0-D array."""
        ds = xr.Dataset({"count": xr.DataArray(42)})

        @dataclass
        class TestSchema(Schema):
            count: Mapping = NameMapping("count")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_scalar(ds, mapper.schema.count)

        assert value == 42

    def test_get_scalar_from_scalar_string(self):
        """Test get_scalar retrieves scalar string."""
        ds = xr.Dataset({"name": xr.DataArray("test_name")})

        @dataclass
        class TestSchema(Schema):
            name: Mapping = NameMapping("name")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_scalar(ds, mapper.schema.name)

        assert value == "test_name"

    def test_get_scalar_fails_for_non_scalar(self):
        """Test get_scalar raises error for multi-element array."""
        ds = xr.Dataset({"temp": (["x"], [25.0, 26.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match=r"is not a scalar \(ndim=0\)"):
            mapper.get_scalar(ds, mapper.schema.temp)

    def test_get_shape(self):
        """Test get_shape returns correct shape."""
        ds = xr.Dataset({"temp": (["x", "y"], [[1, 2, 3], [4, 5, 6]])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        shape = mapper.get_shape(ds, mapper.schema.temp)

        assert shape == (2, 3)

    def test_validate_has_field_success(self):
        """Test validate_has_field passes for existing field."""
        ds = xr.Dataset({"temp": (["x"], [25.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Should not raise
        mapper.validate_has_field(mapper.schema.temp)

    def test_validate_has_field_fails(self):
        """Test validate_has_field fails for missing field."""
        ds = xr.Dataset({"temp": (["x"], [25.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            pressure: Mapping = NameMapping("pressure")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="Missing required field"):
            mapper.validate_has_field(mapper.schema.pressure)

    def test_validate_ndim_success(self):
        """Test validate_ndim passes for correct dimensionality."""
        ds = xr.Dataset({"data": (["chan", "freq"], [[1, 2], [3, 4]])})

        @dataclass
        class TestSchema(Schema):
            data: Mapping = NameMapping("data")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Should not raise for 2-D data
        mapper.validate_ndim(ds, mapper.schema.data, expected_ndim=2)

    def test_validate_ndim_fails(self):
        """Test validate_ndim fails for wrong dimensionality."""
        ds = xr.Dataset({"data": (["chan"], [1, 2])})

        @dataclass
        class TestSchema(Schema):
            data: Mapping = NameMapping("data")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="must be 2-D, got 1-D"):
            mapper.validate_ndim(ds, mapper.schema.data, expected_ndim=2)

    def test_validate_has_physical_type_success(self):
        """Test validate_has_physical_type passes for correct type."""
        ds = xr.Dataset({"freq": (["x"], [1.0, 2.0])})
        ds["freq"].attrs["units"] = "GHz"

        @dataclass
        class TestSchema(Schema):
            freq: Mapping = NameMapping("freq")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Should not raise for frequency units
        mapper.validate_has_physical_type(ds, mapper.schema.freq, "frequency")
        mapper.validate_has_physical_type(
            ds,
            mapper.schema.freq,
            u.get_physical_type("frequency"),
        )

    def test_validate_has_physical_type_rejects_unknown_expected_type(self):
        """An invalid expected physical type fails at the validation boundary."""
        ds = xr.Dataset({"freq": ("x", [1.0, 2.0], {"units": "GHz"})})

        @dataclass
        class TestSchema(Schema):
            freq: Mapping = NameMapping("freq")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError):
            mapper.validate_has_physical_type(
                ds,
                mapper.schema.freq,
                "not-a-physical-type",
            )

    def test_validate_has_physical_type_fails_wrong_type(self):
        """Test validate_has_physical_type fails for wrong type."""
        ds = xr.Dataset({"t": (["x"], [1.0, 2.0])})
        ds["t"].attrs["units"] = "s"

        @dataclass
        class TestSchema(Schema):
            t: Mapping = NameMapping("t")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(
            ValueError,
            match="has physical type 'time', expected 'frequency'",
        ):
            mapper.validate_has_physical_type(ds, mapper.schema.t, "frequency")

    def test_validate_has_physical_type_fails_no_units(self):
        """Test validate_has_physical_type fails when no units set."""
        ds = xr.Dataset({"data": (["x"], [1.0, 2.0])})

        @dataclass
        class TestSchema(Schema):
            data: Mapping = NameMapping("data")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="has no units set"):
            mapper.validate_has_physical_type(ds, mapper.schema.data, "frequency")


class TestXarraySourceContract:
    """Test the common Dataset, DataArray, and DataTree source contract."""

    def test_dataarray_payload_coordinates_and_attrs(self):
        """A DataArray exposes its payload, coordinates, and attributes."""
        source = xr.DataArray(
            [1.0, 2.0, 3.0],
            dims="sample",
            coords={"sample": [10, 20, 30]},
            name="signal",
            attrs={"meta": "data-array"},
        )

        mapper = SourceMapper.from_data_source(source)

        assert mapper.schema.signal in mapper
        assert mapper.schema.sample in mapper
        assert mapper.schema.meta in mapper
        assert mapper.get_arr(source, mapper.schema.signal) is source
        assert mapper.get_arr(source, mapper.schema.sample).identical(source["sample"])
        assert mapper.get_value(source, mapper.schema.meta) == "data-array"
        np.testing.assert_array_equal(
            mapper.get_value(source, mapper.schema.signal),
            source.to_numpy(),
        )
        assert mapper.has_arr(source, mapper.schema.signal)
        assert mapper.has_arr(source, mapper.schema.sample)
        assert mapper.has_attr(source, mapper.schema.meta)

    def test_unnamed_dataarray_uses_data_payload_name(self):
        """An unnamed DataArray resolves its payload under the documented fallback."""

        @dataclass
        class UnnamedSchema(Schema):
            data: Mapping = NameMapping("data")

        class UnnamedMapper(XarrayMapper[UnnamedSchema]):
            pass

        source = xr.DataArray([1, 2, 3])
        mapper = UnnamedMapper.from_data_source(source)

        assert mapper.get_arr(source, mapper.schema.data) is source

    def test_datatree_uses_only_current_node(self):
        """A DataTree exposes its current node without searching children."""
        source = xr.DataTree(
            dataset=xr.Dataset(
                {"signal": ("sample", [1.0, 2.0])},
                coords={"sample": [10, 20]},
                attrs={"meta": "root"},
            ),
        )
        source["analysis"] = xr.DataTree(
            dataset=xr.Dataset({"child_only": ("sample", [3.0, 4.0])}),
        )

        mapper = SourceMapper.from_data_source(source)

        assert mapper.schema.signal in mapper
        assert mapper.schema.sample in mapper
        assert mapper.schema.meta in mapper
        assert mapper.schema.child_only not in mapper
        assert mapper.get_arr(source, mapper.schema.signal).identical(
            source.ds["signal"],
        )
        assert mapper.get_value(source, mapper.schema.meta) == "root"
        assert not mapper.has_arr(source, mapper.schema.child_only)

        child = source["analysis"]
        child_mapper = SourceMapper.from_data_source(child)
        assert child_mapper.schema.child_only in child_mapper
        assert child_mapper.get_arr(child, child_mapper.schema.child_only).identical(
            child.ds["child_only"],
        )

    def test_array_and_attr_name_collision_is_operation_specific(self):
        """Generic values prefer attrs while get_arr explicitly selects arrays."""
        source = xr.DataArray(
            [1.0, 2.0],
            dims="sample",
            name="signal",
            attrs={"signal": "metadata"},
        )
        mapper = SourceMapper.from_data_source(source)

        assert mapper.get_value(source, mapper.schema.signal) == "metadata"
        assert mapper.get_arr(source, mapper.schema.signal) is source

    def test_get_arr_is_lazy_and_get_value_materializes(self):
        """Mapper resolution and labeled reads preserve Dask laziness."""
        computed: list[bool] = []

        @delayed
        def make_values() -> np.ndarray:
            computed.append(True)
            return np.array([1.0, 2.0, 3.0])

        values = da.from_delayed(make_values(), shape=(3,), dtype=np.float64)
        source = xr.Dataset({"signal": ("sample", values)})

        mapper = SourceMapper.from_data_source(source)
        assert computed == []

        arr = mapper.get_arr(source, mapper.schema.signal)
        assert isinstance(arr.data, da.Array)
        assert computed == []

        result = mapper.get_value(source, mapper.schema.signal)
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])
        assert computed == [True]
        assert isinstance(source["signal"].data, da.Array)

    def test_get_scalar_materializes_dask_scalar(self):
        """Scalar extraction computes one Dask value through to_numpy()."""

        @dataclass
        class ScalarSchema(Schema):
            count: Mapping = NameMapping("count")

        class ScalarMapper(XarrayMapper[ScalarSchema]):
            pass

        value = da.from_array(np.array(42))
        source = xr.Dataset({"count": xr.DataArray(value)})
        mapper = ScalarMapper.from_data_source(source)

        assert mapper.get_scalar(source, mapper.schema.count) == 42
        assert isinstance(source["count"].data, da.Array)
