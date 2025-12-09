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
