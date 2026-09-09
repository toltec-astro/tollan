"""Tests for netCDF4 mapper implementation."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pytest

from tollan.accessor.netcdf4 import NetCDF4Mapper
from tollan.accessor.schema import Mapping, NameMapping, Schema

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
    def temp_netcdf(self, tmp_path):
        """Create temporary netCDF file."""
        path = tmp_path / "test.nc"

        with nc.Dataset(path, "w") as ds:
            ds.createDimension("x", 3)
            ds.createDimension("dimension_only", 2)

            coord_var = ds.createVariable("x", "i4", ("x",))
            coord_var[:] = [10, 20, 30]

            temp_var = ds.createVariable("temperature", "f4", ("x",))
            temp_var[:] = [25.0, 26.0, 27.0]

            masked_var = ds.createVariable(
                "masked",
                "f4",
                ("x",),
                fill_value=-999.0,
            )
            masked_var[:] = np.ma.array(
                [1.0, 2.0, 3.0],
                mask=[False, True, False],
            )

            scaled_var = ds.createVariable("scaled", "i2", ("x",))
            scaled_var.scale_factor = 0.5
            scaled_var.add_offset = 10.0
            scaled_var.set_auto_maskandscale(False)
            scaled_var[:] = np.array([0, 2, 4], dtype=np.int16)

            scalar_var = ds.createVariable("observation_id", "i4")
            scalar_var.assignValue(42)

            collision_var = ds.createVariable("close", "i4", ("x",))
            collision_var[:] = [1, 2, 3]
            ds.setncattr("close", "attribute_value")
            ds.setncattr("metadata_field", "metadata_value")

        return path

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_from_dataset(self, temp_netcdf):
        """Create mapper from netCDF4 Dataset."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                temp: Mapping = NameMapping("temperature")

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
                temp: Mapping = NameMapping("temperature")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.temp)

            assert isinstance(value, np.ndarray)
            np.testing.assert_allclose(value, [25.0, 26.0, 27.0])

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_attrs(self, temp_netcdf):
        """Read values from Dataset attributes."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                meta: Mapping = NameMapping("metadata_field")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.meta)

            assert value == "metadata_value"

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_dimension_size(
        self,
        temp_netcdf,
    ):
        """A bare dimension reads as its current length."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                dimension: Mapping = NameMapping(
                    "dimension_only",
                    resolve_value=True,
                )

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            assert mapper.schema.dimension in mapper
            assert mapper.has_dim(ds, mapper.schema.dimension)
            assert mapper.get_dim(ds, mapper.schema.dimension) == 2
            assert mapper.get_value(ds, mapper.schema.dimension) == 2
            assert mapper.mapped_fields[mapper.schema.dimension].value == 2

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_coordinate_variable(self, temp_netcdf):
        """A coordinate variable remains an ordinary readable variable."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                coordinate: Mapping = NameMapping("x")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            assert mapper.has_dim(ds, mapper.schema.coordinate)
            assert mapper.get_dim(ds, mapper.schema.coordinate) == 3
            np.testing.assert_array_equal(
                mapper.get_value(ds, mapper.schema.coordinate),
                [10, 20, 30],
            )

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_global_attribute_precedes_variable_and_api_member(self, temp_netcdf):
        """The netCDF attribute API disambiguates reserved Python names."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                collision: Mapping = NameMapping("close")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            assert callable(ds.close)
            assert mapper.get_value(ds, mapper.schema.collision) == "attribute_value"

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_preserves_mask(self, temp_netcdf):
        """Native variable reads preserve netCDF4 fill-value masking."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                masked: Mapping = NameMapping("masked")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.masked)

            assert np.ma.isMaskedArray(value)
            np.testing.assert_array_equal(value.mask, [False, True, False])
            np.testing.assert_allclose(value.compressed(), [1.0, 3.0])

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_preserves_automatic_scaling(self, temp_netcdf):
        """Native variable reads retain scale-factor and offset decoding."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                scaled: Mapping = NameMapping("scaled")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            np.testing.assert_allclose(
                mapper.get_value(ds, mapper.schema.scaled),
                [10.0, 11.0, 12.0],
            )

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_read_scalar_variable(self, temp_netcdf):
        """Ellipsis indexing reads a zero-dimensional netCDF variable."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                observation_id: Mapping = NameMapping("observation_id")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)
            value = mapper.get_value(ds, mapper.schema.observation_id)

            assert np.asanyarray(value).shape == ()
            assert value.item() == 42

    @pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
    def test_missing_field(self, temp_netcdf):
        """Missing field raises KeyError."""

        with nc.Dataset(temp_netcdf, "r") as ds:

            @dataclass
            class TestSchema(Schema):
                pressure: Mapping = NameMapping("pressure")

            class TestMapper(NetCDF4Mapper[TestSchema]):
                pass

            mapper = TestMapper.from_data_source(ds)

            with pytest.raises(KeyError, match="Field not found"):
                mapper.get_value(ds, mapper.schema.pressure)
