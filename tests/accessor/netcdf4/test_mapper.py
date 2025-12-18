"""Tests for netCDF4 mapper implementation."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

import numpy as np
import pytest
from pydantic.dataclasses import dataclass

from tollan.accessor.netcdf4 import NetCDF4Mapper
from tollan.accessor.schema import Mapping, Schema

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="numpy.ndarray size changed",
        category=RuntimeWarning,
    )
    import netCDF4 as nc  # noqa: N813


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
