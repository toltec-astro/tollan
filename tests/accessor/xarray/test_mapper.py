"""Tests for xarray mapper implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from astropy import units as u
from dask import delayed

from tollan.accessor.schema import NameMapping, Schema
from tollan.accessor.xarray import XarrayAccessorBase, XarrayMapper, ensure_dataset

if TYPE_CHECKING:
    from tollan.accessor.schema import Mapping


@dataclass
class SourceSchema(Schema):
    """Schema shared by the xarray source-contract tests."""

    signal: Mapping = NameMapping.var("signal")
    sample: Mapping = NameMapping.var("sample")
    n_sample: Mapping = NameMapping.dim("sample")
    meta: Mapping = NameMapping("meta")
    child_only: Mapping = NameMapping("child_only")


class SourceMapper(XarrayMapper[SourceSchema]):
    """Mapper shared by the xarray source-contract tests."""


class SourceAccessor(XarrayAccessorBase[SourceMapper]):
    """Select payloads before calling the shared mapper."""


@pytest.mark.parametrize("size", [0, 3])
@pytest.mark.parametrize("source_kind", ["dataset", "dataarray", "wrapped", "tree"])
def test_dimension_without_coordinate(size, source_kind):
    """Dimension lengths need neither a coordinate nor a payload read."""

    @delayed
    def payload():
        pytest.fail("Dimension lookup must not read array values")

    source = xr.DataArray(
        da.from_delayed(payload(), shape=(size,), dtype=float),
        dims="sample",
        name="signal",
    )
    if source_kind == "dataset":
        source = source.to_dataset()
    elif source_kind == "wrapped":
        source = ensure_dataset(source)
    elif source_kind == "tree":
        source = xr.DataTree(source.to_dataset())
    accessor = SourceAccessor(source)
    source = accessor.data_source
    mapper = accessor.mapper
    field = mapper.schema.n_sample
    assert field in mapper
    assert mapper.has_dim(source, field)
    assert mapper.get_dim(source, field) == size
    assert mapper.get_value(source, field) == size
    assert mapper.get_scalar(source, field) == size
    assert not mapper.has_arr(source, field)
    with pytest.raises(ValueError, match="not found as a variable"):
        mapper.get_arr(source, field)
    assert not mapper.has_dim(source, mapper.schema.child_only)
    with pytest.raises(KeyError, match="Dimension not found"):
        mapper.get_dim(source, mapper.schema.child_only)
    with pytest.raises(KeyError, match="Dimension not found"):
        mapper.get_dim(source, mapper.schema.signal)


def test_dimension_and_coordinate_reads_are_distinct():
    """A coordinate's values and a same-named attribute do not affect its size."""
    ds = xr.Dataset(coords={"sample": [10, 20, 30]})
    mapper = SourceMapper.from_data_source(ds)
    field = mapper.schema.sample
    count = mapper.schema.n_sample
    assert mapper.get_dim(ds, count) == 3
    assert not mapper.has_dim(ds, field)
    np.testing.assert_array_equal(mapper.get_value(ds, field), [10, 20, 30])
    with pytest.raises(ValueError, match="not a scalar"):
        mapper.get_scalar(ds, field)
    ds.attrs["sample"] = "attribute"
    np.testing.assert_array_equal(mapper.get_value(ds, field), [10, 20, 30])
    assert mapper.get_dim(ds, count) == 3
    np.testing.assert_array_equal(mapper.get_arr(ds, field), [10, 20, 30])
    assert mapper.get_dim(ds.isel(sample=slice(0, 2)), count) == 2


@pytest.mark.parametrize(
    "value",
    [
        " text ",
        b" text\x00 ",
        np.array([b" text\x00 "]),
        np.array(list(" text\x00 "), dtype="S1"),
        np.array(list(" text\x00 "), dtype="U1"),
        np.array(["text"], dtype=object),
    ],
)
@pytest.mark.parametrize("as_attr", [False, True])
def test_get_str(value, as_attr):
    ds = xr.Dataset()
    if as_attr:
        ds.attrs["meta"] = value
    else:
        ds["meta"] = xr.DataArray(value)
    mapper = SourceMapper.from_data_source(ds)
    assert mapper.get_str(ds, mapper.schema.meta) == "text"


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (123, TypeError),
        ([123], TypeError),
        (["one", "two"], ValueError),
        ([["a", "b"]], ValueError),
    ],
)
def test_get_str_rejects_non_string_or_multiple_strings(value, error):
    ds = xr.Dataset({"meta": xr.DataArray(value)})
    mapper = SourceMapper.from_data_source(ds)
    with pytest.raises(error, match="not a single string"):
        mapper.get_str(ds, mapper.schema.meta)


def test_get_str_preserves_scalar_bytes_contract_and_supports_encoding():
    encoded = "café".encode("latin-1")
    ds = xr.Dataset({"meta": encoded})
    mapper = SourceMapper.from_data_source(ds)
    assert mapper.get_scalar(ds, mapper.schema.meta) == encoded
    assert mapper.get_str(ds, mapper.schema.meta, encoding="latin-1") == "café"
    with pytest.raises(UnicodeDecodeError):
        mapper.get_str(ds, mapper.schema.meta)


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
            time: Mapping = NameMapping.var("time")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        value = mapper.get_value(ds, mapper.schema.time)

        # XarrayMapper returns .values (numpy array), not DataArray
        assert isinstance(value, np.ndarray)
        assert len(value) == 2

    def test_get_attrs(self):
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

    def test_has_var(self):
        """Test has_arr checks for data variables and coordinates."""
        ds = xr.Dataset(
            {"temp": (["x"], [25.0, 26.0])},
            coords={"x": [0, 1]},
        )
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            x: Mapping = NameMapping.var("x")
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
            x: Mapping = NameMapping.var("x")
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

    def test_get_var_with_data_variable(self):
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

    def test_get_var_with_coordinate(self):
        """Test get_arr retrieves DataArray for coordinate."""
        ds = xr.Dataset(
            {"data": (["x"], [1, 2, 3])},
            coords={"x": [0.0, 1.0, 2.0]},
        )

        @dataclass
        class TestSchema(Schema):
            x: Mapping = NameMapping.var("x")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)
        arr = mapper.get_arr(ds, mapper.schema.x)

        assert isinstance(arr, xr.DataArray)
        assert len(arr) == 3
        assert arr.values[0] == 0.0

    def test_get_var_with_attribute_fails(self):
        """Test get_arr raises error for attribute."""
        ds = xr.Dataset({"data": (["x"], [1, 2])})
        ds.attrs["meta"] = "value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = NameMapping("meta")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(ds)

        with pytest.raises(ValueError, match="not found as a variable in Dataset"):
            mapper.get_arr(ds, mapper.schema.meta)

    def test_get_var_from_dataarray_with_coordinate(self):
        """Test get_arr retrieves coordinate from DataArray."""
        ds = xr.Dataset(
            {"temp": (["x", "y"], [[1, 2], [3, 4]])},
            coords={"x": [0.0, 1.0], "y": [10.0, 20.0]},
        )

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            x: Mapping = NameMapping.var("x")
            y: Mapping = NameMapping.var("y")

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

    def test_get_var_from_dataarray_fails_for_nonexistent_coord(self):
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
        with pytest.raises(ValueError, match="not found as a variable in DataArray"):
            mapper.get_arr(temp_da, mapper.schema.z)

    def test_get_var_dataset_vs_dataarray_coordinate_access(self):
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
            chan: Mapping = NameMapping.var("chan")
            freq: Mapping = NameMapping.var("freq")

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
        """The accessor selects the DataTree node before mapper operations."""
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

        with pytest.raises(TypeError, match="payload"):
            SourceMapper.from_data_source(source)  # ty: ignore[invalid-argument-type]
        accessor = SourceAccessor(source)
        mapper = accessor.mapper
        payload = accessor.data_source
        assert mapper.schema.signal in mapper
        assert mapper.schema.sample in mapper
        assert mapper.schema.meta in mapper
        assert mapper.schema.child_only not in mapper
        assert mapper.get_arr(payload, mapper.schema.signal).identical(
            source.ds["signal"],
        )
        assert mapper.get_value(payload, mapper.schema.meta) == "root"
        assert not mapper.has_arr(payload, mapper.schema.child_only)

        child = source["analysis"]
        child_accessor = SourceAccessor(child)
        child_mapper = child_accessor.mapper
        assert child_mapper.schema.child_only in child_mapper
        assert child_mapper.get_arr(
            child_accessor.data_source, child_mapper.schema.child_only
        ).identical(
            child.ds["child_only"],
        )

    def test_array_mapping_does_not_switch_to_same_named_attribute(self):
        """All reads honor the location selected by the mapping."""
        source = xr.DataArray(
            [1.0, 2.0],
            dims="sample",
            name="signal",
            attrs={"signal": "metadata"},
        )
        mapper = SourceMapper.from_data_source(source)

        np.testing.assert_array_equal(
            mapper.get_value(source, mapper.schema.signal), [1.0, 2.0]
        )
        assert not mapper.has_attr(source, mapper.schema.signal)
        assert mapper.get_arr(source, mapper.schema.signal) is source

    def test_get_var_is_lazy_and_get_value_materializes(self):
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

    def test_get_scalar_rejects_array_before_computing(self):
        @delayed
        def values():
            pytest.fail("A non-scalar array must be rejected before reading values")

        source = xr.Dataset(
            {"signal": ("sample", da.from_delayed(values(), shape=(3,), dtype=float))}
        )
        mapper = SourceMapper.from_data_source(source)
        with pytest.raises(ValueError, match="not a scalar"):
            mapper.get_scalar(source, mapper.schema.signal)
