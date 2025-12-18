"""Tests for xarray-specific accessor components."""

from __future__ import annotations

import functools

import numpy as np
import pytest
import xarray as xr
from pydantic.dataclasses import dataclass

from tollan.accessor import Mapping, Schema
from tollan.accessor.xarray import (
    XarrayAccessorBase,
    XarrayMapper,
    ensure_dataset,
    ensure_datatree,
)

# Random number generator for reproducible tests
rng = np.random.default_rng(42)

# Check for optional dependencies
try:
    import zarr  # noqa: F401

    HAS_ZARR = True
except ImportError:
    HAS_ZARR = False

try:
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        import netCDF4  # noqa: F401

    HAS_NETCDF4 = True
except (ImportError, RuntimeWarning):
    HAS_NETCDF4 = False


class TestEnsureDataset:
    """Test ensure_dataset utility function."""

    def test_dataset_passthrough(self):
        """Dataset is returned as-is."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        result = ensure_dataset(ds)
        assert result is ds

    def test_datatree_to_dataset(self):
        """DataTree returns root dataset."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")
        result = ensure_dataset(dt)

        assert isinstance(result, xr.Dataset)
        assert result.equals(dt.ds)
        assert "temp" in result

    def test_dataarray_to_dataset(self):
        """DataArray is wrapped in Dataset."""
        da = xr.DataArray([20.0, 21.0, 22.0], name="temp")
        result = ensure_dataset(da)

        assert isinstance(result, xr.Dataset)
        assert "temp" in result
        assert result["temp"].equals(da)

    def test_dataarray_without_name(self):
        """DataArray without name uses default 'data'."""
        da = xr.DataArray([20.0, 21.0, 22.0])
        result = ensure_dataset(da)

        assert isinstance(result, xr.Dataset)
        assert "data" in result

    def test_invalid_type(self):
        """Invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Expected Dataset, DataArray, or DataTree"):
            ensure_dataset("not a valid type")  # type: ignore[arg-type]


class TestEnsureDataTree:
    """Test ensure_datatree utility function."""

    def test_datatree_passthrough(self):
        """DataTree is returned as-is."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")
        result = ensure_datatree(dt)
        assert result is dt

    def test_dataset_to_datatree(self):
        """Dataset is wrapped in DataTree."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        result = ensure_datatree(ds)

        assert isinstance(result, xr.DataTree)
        assert result.name == "root"
        assert result.ds.equals(ds)  # pyright: ignore[reportArgumentType]

    def test_dataarray_to_datatree(self):
        """DataArray is wrapped in Dataset then DataTree."""
        da = xr.DataArray([20.0, 21.0, 22.0], name="temp")
        result = ensure_datatree(da)

        assert isinstance(result, xr.DataTree)
        assert result.name == "root"
        assert "temp" in result.ds

    def test_dataarray_without_name(self):
        """DataArray without name uses default 'data'."""
        da = xr.DataArray([20.0, 21.0, 22.0])
        result = ensure_datatree(da)

        assert isinstance(result, xr.DataTree)
        assert "data" in result.ds

    def test_invalid_type(self):
        """Invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Expected Dataset, DataArray, or DataTree"):
            ensure_datatree("not a valid type")  # type: ignore[arg-type]


class TestRoundTrip:
    """Test round-trip conversions."""

    def test_dataset_roundtrip(self):
        """Dataset → DataTree → Dataset preserves data."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = ensure_datatree(ds)
        ds2 = ensure_dataset(dt)

        assert ds.equals(ds2)

    def test_datatree_roundtrip(self):
        """DataTree → Dataset → DataTree preserves data."""
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")
        ds2 = ensure_dataset(dt)
        dt2 = ensure_datatree(ds2)

        assert dt.ds.equals(dt2.ds)


class TestXarrayAccessorBaseCreation:
    """Test XarrayAccessorBase initialization."""

    @dataclass
    class MySchema(Schema):
        temp: Mapping = Mapping("temp")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    def test_with_dataset(self):
        """XarrayAccessorBase with Dataset."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        accessor = TestAccessor(ds)

        assert isinstance(accessor._data_source, xr.Dataset)
        assert isinstance(accessor.data_source, xr.Dataset)
        assert accessor.data_source is ds
        assert isinstance(accessor.mapper, self.MyMapper)

    def test_with_datatree(self):
        """XarrayAccessorBase with DataTree."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")
        accessor = TestAccessor(dt)

        # Stores original DataTree
        assert isinstance(accessor._data_source, xr.DataTree)
        assert accessor._data_source is dt

        # Resolves to Dataset
        assert isinstance(accessor.data_source, xr.Dataset)
        assert accessor.data_source.equals(dt.ds)

    def test_with_dataarray(self):
        """XarrayAccessorBase with DataArray."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        da = xr.DataArray([20.0, 21.0, 22.0], name="temp")
        accessor = TestAccessor(da)

        assert isinstance(accessor._data_source, xr.DataArray)
        assert isinstance(accessor.data_source, xr.Dataset)
        assert "temp" in accessor.data_source

    def test_with_provided_mapper(self):
        """XarrayAccessorBase accepts pre-created mapper."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        mapper = self.MyMapper.from_data_source(ds)
        accessor = TestAccessor(ds, mapper)

        assert accessor.mapper is mapper


class TestXarrayAccessorBaseResolution:
    """Test data_source resolution in XarrayAccessorBase."""

    @dataclass
    class MySchema(Schema):
        temp: Mapping = Mapping("temp")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    def test_default_resolution_dataset(self):
        """Default resolution with Dataset."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        accessor = TestAccessor(ds)

        # data_source should be same as _data_source for Dataset
        assert accessor.data_source is accessor._data_source

    def test_default_resolution_datatree(self):
        """Default resolution with DataTree extracts root dataset."""

        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            pass

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")
        accessor = TestAccessor(dt)

        # data_source should be resolved to Dataset
        assert accessor._data_source is dt
        assert accessor.data_source.equals(dt.ds)

    def test_custom_resolution(self):
        """Custom resolution can override data_source property."""

        class CustomAccessor(XarrayAccessorBase[self.MyMapper]):
            @functools.cached_property
            def data_source(self):
                """Custom resolution: look for 'analysis' child."""
                if isinstance(self._data_source, xr.DataTree):
                    for child in self._data_source.children.values():
                        if child.name == "analysis":
                            return child.ds
                    msg = "No analysis child found"
                    raise ValueError(msg)
                return ensure_dataset(self._data_source)

        # Create DataTree with child
        root_ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset({"result": (["x"], [1.0, 2.0, 3.0])})
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        accessor = CustomAccessor(dt)

        # Should resolve to child dataset
        assert isinstance(accessor.data_source, xr.Dataset)
        assert accessor.data_source.equals(child_ds)  # pyright: ignore[reportArgumentType]
        assert "result" in accessor.data_source
        assert "temp" not in accessor.data_source

    def test_custom_resolution_error(self):
        """Custom resolution raises error when child not found."""

        class CustomAccessor(XarrayAccessorBase[self.MyMapper]):
            @functools.cached_property
            def data_source(self):  # pyright: ignore[reportIncompatibleVariableOverride]
                """Custom resolution: look for 'analysis' child."""
                if isinstance(self._data_source, xr.DataTree):
                    for child in self._data_source.children.values():
                        if child.name == "analysis":
                            return child.ds
                    msg = "No analysis child found"
                    raise ValueError(msg)
                return ensure_dataset(self._data_source)

        # Create DataTree without analysis child
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")

        # Should raise error during initialization (when creating mapper)
        with pytest.raises(ValueError, match="No analysis child found"):
            accessor = CustomAccessor(dt)


class TestXarrayAccessorBaseDualRegistration:
    """Test dual registration for Dataset and DataTree."""

    @dataclass
    class MySchema(Schema):
        temp: Mapping = Mapping("temp")
        pressure: Mapping = Mapping("pressure")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    def test_dataset_accessor(self):
        """Accessor registered for Dataset."""

        @xr.register_dataset_accessor("test_accessor")
        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_mean(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return float(temp.mean())

        ds = xr.Dataset(
            {
                "temp": (["x"], [20.0, 21.0, 22.0]),
                "pressure": (["x"], [101.0, 102.0, 103.0]),
            },
        )

        # Should have accessor
        assert hasattr(ds, "test_accessor")
        assert ds.test_accessor.temp_mean == 21.0

        # Cleanup
        del xr.Dataset.test_accessor  # type: ignore[attr-defined]

    def test_datatree_accessor(self):
        """Accessor registered for DataTree."""

        @xr.register_datatree_accessor("test_accessor")
        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_mean(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return float(temp.mean())

        ds = xr.Dataset(
            {
                "temp": (["x"], [20.0, 21.0, 22.0]),
                "pressure": (["x"], [101.0, 102.0, 103.0]),
            },
        )
        dt = xr.DataTree(dataset=ds, name="root")

        # Should have accessor
        assert hasattr(dt, "test_accessor")
        assert dt.test_accessor.temp_mean == 21.0

        # Cleanup
        del xr.DataTree.test_accessor  # type: ignore[attr-defined]

    def test_dual_registration(self):
        """Accessor registered for both Dataset and DataTree."""

        @xr.register_dataset_accessor("test_accessor")
        @xr.register_datatree_accessor("test_accessor")
        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_mean(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return float(temp.mean())

        ds = xr.Dataset(
            {
                "temp": (["x"], [20.0, 21.0, 22.0]),
                "pressure": (["x"], [101.0, 102.0, 103.0]),
            },
        )
        dt = xr.DataTree(dataset=ds, name="root")

        # Both should have accessor
        assert hasattr(ds, "test_accessor")
        assert hasattr(dt, "test_accessor")

        # Both should return same result
        assert ds.test_accessor.temp_mean == 21.0
        assert dt.test_accessor.temp_mean == 21.0

        # Cleanup
        del xr.Dataset.test_accessor  # type: ignore[attr-defined]
        del xr.DataTree.test_accessor  # type: ignore[attr-defined]


class TestXarrayAccessorBaseViews:
    """Test view pattern with XarrayAccessorBase."""

    @dataclass
    class MySchema(Schema):
        temp: Mapping = Mapping("temp")
        result: Mapping = Mapping("result")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    def test_view_with_default_resolution(self):
        """View inherits default resolution."""

        class DefaultView(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_celsius(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return temp.values

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")

        # View with Dataset
        view_ds = DefaultView(ds)
        assert view_ds.temp_celsius.tolist() == [20.0, 21.0, 22.0]

        # View with DataTree (resolves to root)
        view_dt = DefaultView(dt)
        assert view_dt.temp_celsius.tolist() == [20.0, 21.0, 22.0]

    def test_view_with_custom_resolution(self):
        """View with custom resolution for child nodes."""

        class ChildView(XarrayAccessorBase[self.MyMapper]):
            @functools.cached_property
            def data_source(self):
                """Resolve to 'analysis' child."""
                if isinstance(self._data_source, xr.DataTree):
                    for child in self._data_source.children.values():
                        if child.name == "analysis":
                            return child.ds
                    msg = "No analysis child"
                    raise ValueError(msg)
                return ensure_dataset(self._data_source)

            @property
            def result_data(self):
                result = self.mapper.get_arr(
                    self.data_source,
                    self.mapper.schema.result,
                )
                return result.values

        # Create DataTree with analysis child
        root_ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset({"result": (["x"], [1.0, 2.0, 3.0])})
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        # View should access child
        view = ChildView(dt)
        assert view.result_data.tolist() == [1.0, 2.0, 3.0]

    def test_accessor_passes_original_to_view(self):
        """Accessor passes _data_source to views (Option C pattern)."""

        class MyView(XarrayAccessorBase[self.MyMapper]):
            pass

        class MyAccessor(XarrayAccessorBase[self.MyMapper]):
            @functools.cached_property
            def my_view(self):
                # Should pass _data_source (original)
                return MyView(self._data_source, self.mapper)

        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=ds, name="root")

        # With Dataset
        accessor_ds = MyAccessor(ds)
        view_ds = accessor_ds.my_view
        assert view_ds._data_source is ds

        # With DataTree
        accessor_dt = MyAccessor(dt)
        view_dt = accessor_dt.my_view
        assert view_dt._data_source is dt


class TestXarrayAccessorBaseChildNodes:
    """Test working with DataTree child nodes."""

    @dataclass
    class DataSchema(Schema):
        real: Mapping = Mapping("real")
        imag: Mapping = Mapping("imag")
        result: Mapping = Mapping("result")

    class DataMapper(XarrayMapper[DataSchema]):
        pass

    def test_create_child_node(self):
        """Create child node in DataTree."""
        # Create root
        root_ds = xr.Dataset(
            {
                "real": (["det", "tone"], rng.standard_normal((10, 5))),
                "imag": (["det", "tone"], rng.standard_normal((10, 5))),
            },
        )
        dt = xr.DataTree(dataset=root_ds, name="root")

        # Add child
        child_ds = xr.Dataset(
            {
                "result": (["det", "tone"], rng.standard_normal((10, 5))),
            },
        )
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        # Verify structure
        assert "analysis" in [c.name for c in dt.children.values()]
        assert "real" in dt.ds
        assert "imag" in dt.ds
        assert "result" in dt["/analysis"].ds

    def test_accessor_with_child_nodes(self):
        """Accessor working with child nodes."""

        class RootView(XarrayAccessorBase[self.DataMapper]):
            @property
            def complex_data(self):
                real_part = self.mapper.get_arr(
                    self.data_source,
                    self.mapper.schema.real,
                )
                imag_part = self.mapper.get_arr(
                    self.data_source,
                    self.mapper.schema.imag,
                )
                return real_part.values + 1j * imag_part.values

        class AnalysisView(XarrayAccessorBase[self.DataMapper]):
            @functools.cached_property
            def data_source(self):
                """Resolve to analysis child."""
                if isinstance(self._data_source, xr.DataTree):
                    for child in self._data_source.children.values():
                        if child.name == "analysis":
                            return child.ds
                    msg = "No analysis found"
                    raise ValueError(msg)
                return ensure_dataset(self._data_source)

            @property
            def result_data(self):
                result = self.mapper.get_arr(
                    self.data_source,
                    self.mapper.schema.result,
                )
                return result.values

        @xr.register_datatree_accessor("data")
        class DataAccessor(XarrayAccessorBase[self.DataMapper]):
            @functools.cached_property
            def root(self):
                return RootView(self._data_source, self.mapper)

            @functools.cached_property
            def analysis(self):
                return AnalysisView(self._data_source, self.mapper)

        # Create DataTree with child
        root_ds = xr.Dataset(
            {
                "real": (["det", "tone"], np.ones((10, 5))),
                "imag": (["det", "tone"], np.ones((10, 5)) * 2),
            },
        )
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset(
            {
                "result": (["det", "tone"], np.ones((10, 5)) * 3),
            },
        )
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        # Access via accessor
        assert dt.data.root.complex_data.shape == (10, 5)
        assert dt.data.analysis.result_data.shape == (10, 5)
        assert np.allclose(dt.data.analysis.result_data, 3.0)

        # Cleanup
        del xr.DataTree.data  # type: ignore[attr-defined]


class TestXarrayAccessorBaseValidation:
    """Test validation in XarrayAccessorBase."""

    @dataclass
    class MySchema(Schema):
        required_field: Mapping = Mapping("required")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    def test_validation_called(self):
        """_validate is called during initialization."""
        validation_called = []

        class ValidatingAccessor(XarrayAccessorBase[self.MyMapper]):
            def _validate(self):
                validation_called.append(True)

        ds = xr.Dataset({"required": (["x"], [1, 2, 3])})
        accessor = ValidatingAccessor(ds)

        assert len(validation_called) == 1

    def test_validation_can_raise(self):
        """_validate can raise errors."""

        class ValidatingAccessor(XarrayAccessorBase[self.MyMapper]):
            def _validate(self):
                if self.mapper.schema.required_field not in self.mapper:
                    msg = "Missing required field"
                    raise ValueError(msg)

        # Should succeed with required field
        ds_valid = xr.Dataset({"required": (["x"], [1, 2, 3])})
        accessor = ValidatingAccessor(ds_valid)
        assert accessor is not None

        # Should fail without required field
        ds_invalid = xr.Dataset({"other": (["x"], [1, 2, 3])})
        with pytest.raises(ValueError, match="Missing required field"):
            ValidatingAccessor(ds_invalid)


class TestNetCDFFileIO:
    """Test netcdf save/load operations."""

    @dataclass
    class MySchema(Schema):
        temp: Mapping = Mapping("temp")
        pressure: Mapping = Mapping("pressure")

    class MyMapper(XarrayMapper[MySchema]):
        pass

    @pytest.mark.skipif(not HAS_NETCDF4, reason="netCDF4 not installed")
    def test_dataset_save_load_netcdf(self, tmp_path):
        """Dataset can be saved and loaded from netcdf."""
        # Create dataset
        ds = xr.Dataset(
            {
                "temp": (["x", "y"], [[20.0, 21.0], [22.0, 23.0]]),
                "pressure": (["x", "y"], [[101.0, 102.0], [103.0, 104.0]]),
            },
        )

        # Save to netcdf
        filepath = tmp_path / "test.nc"
        ds.to_netcdf(filepath)

        # Load back
        ds_loaded = xr.open_dataset(filepath)

        # Should have same data
        assert ds_loaded.equals(ds)

        # Cleanup
        ds_loaded.close()

    @pytest.mark.skipif(not HAS_NETCDF4, reason="netCDF4 not installed")
    def test_dataset_with_accessor_after_load(self, tmp_path):
        """Accessor works after loading from netcdf."""

        @xr.register_dataset_accessor("test_accessor")
        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_mean(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return float(temp.mean())

        # Create and save
        ds = xr.Dataset(
            {
                "temp": (["x"], [20.0, 21.0, 22.0]),
                "pressure": (["x"], [101.0, 102.0, 103.0]),
            },
        )
        filepath = tmp_path / "test.nc"
        ds.to_netcdf(filepath)

        # Load and use accessor
        ds_loaded = xr.open_dataset(filepath)
        assert hasattr(ds_loaded, "test_accessor")
        assert ds_loaded.test_accessor.temp_mean == 21.0

        # Cleanup
        ds_loaded.close()
        del xr.Dataset.test_accessor  # type: ignore[attr-defined]

    @pytest.mark.skipif(not HAS_ZARR, reason="zarr not installed")
    def test_datatree_save_load_zarr(self, tmp_path):
        """DataTree can be saved and loaded from zarr."""
        # Create datatree with children
        root_ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset({"result": (["x"], [1.0, 2.0, 3.0])})
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        # Save to zarr
        zarr_path = tmp_path / "test.zarr"
        dt.to_zarr(zarr_path)

        # Load back
        dt_loaded = xr.open_datatree(zarr_path, engine="zarr")

        # Should have same structure
        assert "analysis" in [c.name for c in dt_loaded.children.values()]
        assert dt_loaded.ds.equals(root_ds)  # pyright: ignore[reportArgumentType]
        assert dt_loaded["/analysis"].ds.equals(child_ds)  # pyright: ignore[reportArgumentType]

    @pytest.mark.skipif(not HAS_ZARR, reason="zarr not installed")
    def test_datatree_with_accessor_after_load(self, tmp_path):
        """Accessor works with DataTree after loading from zarr."""

        @xr.register_datatree_accessor("test_accessor")
        class TestAccessor(XarrayAccessorBase[self.MyMapper]):
            @property
            def temp_mean(self):
                temp = self.mapper.get_arr(self.data_source, self.mapper.schema.temp)
                return float(temp.mean())

        # Create and save
        root_ds = xr.Dataset(
            {
                "temp": (["x"], [20.0, 21.0, 22.0]),
                "pressure": (["x"], [101.0, 102.0, 103.0]),
            },
        )
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset({"result": (["x"], [1.0, 2.0, 3.0])})
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        zarr_path = tmp_path / "test.zarr"
        dt.to_zarr(zarr_path)

        # Load and use accessor
        dt_loaded = xr.open_datatree(zarr_path, engine="zarr")
        assert hasattr(dt_loaded, "test_accessor")
        assert dt_loaded.test_accessor.temp_mean == 21.0

        # Cleanup
        del xr.DataTree.test_accessor  # type: ignore[attr-defined]

    @pytest.mark.skipif(not HAS_NETCDF4, reason="netCDF4 not installed")
    def test_ensure_utilities_with_loaded_data(self, tmp_path):
        """ensure_* utilities work with loaded data."""
        # Create and save dataset
        ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        filepath = tmp_path / "test.nc"
        ds.to_netcdf(filepath)

        # Load and use utilities
        ds_loaded = xr.open_dataset(filepath)

        # ensure_dataset should work
        result = ensure_dataset(ds_loaded)
        assert result.equals(ds_loaded)

        # ensure_datatree should work
        dt = ensure_datatree(ds_loaded)
        assert isinstance(dt, xr.DataTree)
        assert dt.ds.equals(ds_loaded)  # pyright: ignore[reportArgumentType]

        # Cleanup
        ds_loaded.close()

    @pytest.mark.skipif(not HAS_ZARR, reason="zarr not installed")
    def test_custom_resolution_after_zarr_load(self, tmp_path):
        """Custom resolution works with loaded DataTree."""

        class AnalysisView(XarrayAccessorBase[self.MyMapper]):
            @functools.cached_property
            def data_source(self):
                """Resolve to analysis child."""
                if isinstance(self._data_source, xr.DataTree):
                    for child in self._data_source.children.values():
                        if child.name == "analysis":
                            return child.ds
                    msg = "No analysis found"
                    raise ValueError(msg)
                return ensure_dataset(self._data_source)

            @property
            def result_values(self):
                # Access result from child
                return self.data_source["result"].values

        # Create and save datatree
        root_ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
        dt = xr.DataTree(dataset=root_ds, name="root")

        child_ds = xr.Dataset({"result": (["x"], [1.0, 2.0, 3.0])})
        dt["/analysis"] = xr.DataTree(dataset=child_ds, name="analysis")

        zarr_path = tmp_path / "test.zarr"
        dt.to_zarr(zarr_path)

        # Load and use custom resolution
        dt_loaded = xr.open_datatree(zarr_path, engine="zarr")
        view = AnalysisView(dt_loaded)
        assert view.result_values.tolist() == [1.0, 2.0, 3.0]
