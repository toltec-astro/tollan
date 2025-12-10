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

    def test_has_var(self):
        """Test has_var checks for data variables only."""
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

        # temp is a data variable
        assert mapper.has_var(ds, mapper.schema.temp)
        # x is a coordinate, not a data variable
        assert not mapper.has_var(ds, mapper.schema.x)
        # meta is an attribute, not a data variable
        assert not mapper.has_var(ds, mapper.schema.meta)

    def test_has_coord(self):
        """Test has_coord checks for coordinates only."""
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

        # x is a coordinate
        assert mapper.has_coord(ds, mapper.schema.x)
        # temp is a data variable, not a coordinate
        assert not mapper.has_coord(ds, mapper.schema.temp)
        # meta is an attribute, not a coordinate
        assert not mapper.has_coord(ds, mapper.schema.meta)

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

    def test_get_coord_success(self):
        """Test get_coord retrieves coordinate DataArray."""
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
        coord = mapper.get_coord(ds, mapper.schema.x)

        assert isinstance(coord, xr.DataArray)
        assert len(coord) == 3
        assert coord.values[0] == 0.0

    def test_get_coord_with_data_variable_fails(self):
        """Test get_coord raises error for data variable."""
        ds = xr.Dataset({"temp": (["x"], [25.0, 26.0])})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="not found as coordinate"):
            mapper.get_coord(ds, mapper.schema.temp)

    def test_get_coord_with_attribute_fails(self):
        """Test get_coord raises error for attribute."""
        ds = xr.Dataset({"data": (["x"], [1, 2])})
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = Mapping("meta")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="not found as coordinate"):
            mapper.get_coord(ds, mapper.schema.meta)


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
