"""Tests for concrete mapper implementations (DataFrame, Xarray, NetCDF4)."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from pydantic.dataclasses import dataclass

from tollan.accessor.mappers import DataFrameMapper, NetCDF4Mapper, XarrayMapper
from tollan.accessor.schema import Mapping, Schema

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="numpy.ndarray size changed",
        category=RuntimeWarning,
    )
    import netCDF4 as nc  # noqa: N813


class TestDataFrameMapper:
    """Test DataFrameMapper for pandas.DataFrame."""

    def test_from_dataframe(self):
        """Create mapper from DataFrame."""
        df = pd.DataFrame({"temp": [25.0, 26.0], "pressure": [101.3, 101.4]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        assert isinstance(mapper, DataFrameMapper)

    def test_read_column_values(self):
        """Read column values as numpy arrays."""
        df = pd.DataFrame({"temp": [25.0, 26.0, 27.0]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.temp)

        assert isinstance(value, np.ndarray)
        assert len(value) == 3
        assert value[0] == 25.0

    def test_read_attrs(self):
        """Read values from DataFrame.attrs."""
        df = pd.DataFrame({"col": [1, 2]})
        df.attrs["metadata_field"] = "metadata_value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = Mapping("metadata_field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.meta)

        assert value == "metadata_value"

    def test_attrs_priority_over_columns(self):
        """attrs take priority over columns with same name."""
        df = pd.DataFrame({"field": [1, 2, 3]})
        df.attrs["field"] = "from_attrs"

        @dataclass
        class TestSchema(Schema):
            field: Mapping = Mapping("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.field)

        # attrs should be checked first
        assert value == "from_attrs"

    def test_missing_field(self):
        """Missing field raises KeyError."""
        df = pd.DataFrame({"temp": [25.0]})

        @dataclass
        class TestSchema(Schema):
            pressure: Mapping = Mapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(df, mapper.schema.pressure)


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


class TestNetCDF4Mapper:
    """Test NetCDF4Mapper for netCDF4.Dataset."""

    @pytest.fixture
    def temp_netcdf(self):
        """Create temporary netCDF file."""

        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
            path = Path(tmp.name)

        # Create netCDF file
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("x", 3)
            temp_var = ds.createVariable("temperature", "f4", ("x",))
            temp_var[:] = [25.0, 26.0, 27.0]
            ds.metadata_field = "metadata_value"

        yield path
        path.unlink()

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_from_dataset(self, temp_netcdf):
        """Create mapper from netCDF4 Dataset."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                temp: Mapping = Mapping("temperature")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            assert isinstance(mapper, NetCDF4Mapper)

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_variable(self, temp_netcdf):
        """Read variable values."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                temp: Mapping = Mapping("temperature")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.temp)

            assert isinstance(value, np.ndarray)
            assert len(value) == 3
            assert value[0] == 25.0

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_attrs(self, temp_netcdf):
        """Read values from Dataset attributes."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                meta: Mapping = Mapping("metadata_field")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.meta)

            assert value == "metadata_value"

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_missing_field(self, temp_netcdf):
        """Missing field raises KeyError."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                pressure: Mapping = Mapping("pressure")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            with pytest.raises(KeyError, match="Field not found"):
                mapper.get_value(ds, mapper.schema.pressure)


class TestMapperInteroperability:
    """Test that all mappers work consistently."""

    def test_consistent_api(self):
        """All mappers have consistent API."""
        # DataFrame
        df = pd.DataFrame({"temp": [25.0]})

        @dataclass
        class EmptySchema(Schema):
            pass

        class TestDFMapper(DataFrameMapper[EmptySchema]):
            pass

        df_mapper = TestDFMapper.from_data_source(df)
        assert hasattr(df_mapper, "get_value")
        assert hasattr(df_mapper, "schema")

        # Xarray
        ds = xr.Dataset({"temp": (["x"], [25.0])})

        class TestXRMapper(XarrayMapper[EmptySchema]):
            pass

        xr_mapper = TestXRMapper.from_data_source(ds)
        assert hasattr(xr_mapper, "get_value")
        assert hasattr(xr_mapper, "schema")

    def test_same_schema_different_sources(self):
        """Same schema works with different data sources."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        # DataFrame
        df = pd.DataFrame({"temp": [25.0]})

        class TestDFMapper(DataFrameMapper[TestSchema]):
            pass

        df_mapper = TestDFMapper.from_data_source(df)
        df_value = df_mapper.get_value(df, df_mapper.schema.temp)

        # Xarray
        ds = xr.Dataset({"temp": (["x"], [25.0])})

        class TestXRMapper(XarrayMapper[TestSchema]):
            pass

        xr_mapper = TestXRMapper.from_data_source(ds)
        xr_value = xr_mapper.get_value(ds, xr_mapper.schema.temp)

        # Both should resolve successfully
        assert df_value[0] == 25.0
        assert xr_value[0].item() == 25.0
