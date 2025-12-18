"""Tests for xarray mapper implementation."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from pydantic.dataclasses import dataclass

from tollan.accessor.schema import Mapping, Schema
from tollan.accessor.xarray import XarrayMapper


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
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        assert isinstance(mapper, XarrayMapper)

    def test_read_data_variable(self):
        """Read data variable values as numpy array."""
        ds = xr.Dataset({"temp": (["x"], [25.0, 26.0, 27.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

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
            time: Mapping = Mapping("time")

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
            meta: Mapping = Mapping("metadata_field")

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
            pressure: Mapping = Mapping("pressure")

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
            temp: Mapping = Mapping("temp")
            x: Mapping = Mapping("x")
            meta: Mapping = Mapping("meta")
            missing: Mapping = Mapping("missing")

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
            temp: Mapping = Mapping("temp")
            x: Mapping = Mapping("x")
            meta: Mapping = Mapping("meta")

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
            temp: Mapping = Mapping("temp")

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
            x: Mapping = Mapping("x")

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
            meta: Mapping = Mapping("meta")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="not found in dataset"):
            mapper.get_arr(ds, mapper.schema.meta)

    def test_get_arr_from_dataarray_with_coordinate(self):
        """Test get_arr retrieves coordinate from DataArray."""
        ds = xr.Dataset(
            {"temp": (["x", "y"], [[1, 2], [3, 4]])},
            coords={"x": [0.0, 1.0], "y": [10.0, 20.0]},
        )

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")
            x: Mapping = Mapping("x")
            y: Mapping = Mapping("y")

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
            temp: Mapping = Mapping("temp")
            z: Mapping = Mapping("z")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        temp_da = mapper.get_arr(ds, mapper.schema.temp)

        # Should fail when trying to get non-existent coordinate from DataArray
        with pytest.raises(ValueError, match="not found in data array coords"):
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
            data: Mapping = Mapping("data")
            chan: Mapping = Mapping("chan")
            freq: Mapping = Mapping("freq")

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
            obs_id: Mapping = Mapping("obs_id")

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
            count: Mapping = Mapping("count")

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
            name: Mapping = Mapping("name")

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
            temp: Mapping = Mapping("temp")

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
            temp: Mapping = Mapping("temp")

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
            temp: Mapping = Mapping("temp")

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
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

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
            data: Mapping = Mapping("data")

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
            data: Mapping = Mapping("data")

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
            freq: Mapping = Mapping("freq")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        # Should not raise for frequency units
        mapper.validate_has_physical_type(ds, mapper.schema.freq, "frequency")

    def test_validate_has_physical_type_fails_wrong_type(self):
        """Test validate_has_physical_type fails for wrong type."""
        ds = xr.Dataset({"t": (["x"], [1.0, 2.0])})
        ds["t"].attrs["units"] = "s"

        @dataclass
        class TestSchema(Schema):
            t: Mapping = Mapping("t")

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
            data: Mapping = Mapping("data")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="has no units set"):
            mapper.validate_has_physical_type(ds, mapper.schema.data, "frequency")
