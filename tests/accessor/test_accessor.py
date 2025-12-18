"""Tests for AccessorBase functionality."""

from __future__ import annotations

from typing import Any

import pytest
import xarray as xr
from pydantic.dataclasses import dataclass

from tollan.accessor import AccessorBase, Mapper, Mapping, Schema
from tollan.accessor.xarray import XarrayMapper


class TestAccessorBaseCreation:
    """Test AccessorBase initialization and type detection."""

    def test_with_concrete_mapper_type(self):
        """AccessorBase with concrete mapper type auto-creates mapper."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        accessor = TestAccessor(ds)

        assert isinstance(accessor, TestAccessor)
        assert isinstance(accessor.mapper, TestMapper)
        assert accessor.data_source is ds

    def test_with_provided_mapper(self):
        """AccessorBase accepts pre-created mapper."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        mapper = TestMapper.from_data_source(ds)
        accessor = TestAccessor(ds, mapper)

        assert accessor.mapper is mapper
        assert accessor.data_source is ds

    def test_generic_intermediate_class(self):
        """Generic intermediate class doesn't require concrete mapper."""

        class GenericAccessor[DataSourceT, MapperT: Mapper](
            AccessorBase[DataSourceT, MapperT],
        ):
            pass

        # Should not raise during class definition
        assert GenericAccessor is not None

    def test_mapper_cls_auto_detected(self):
        """Verify _mapper_cls is auto-detected via __init_subclass__."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        # _mapper_cls should be set by __init_subclass__
        assert hasattr(TestAccessor, "_mapper_cls")
        assert TestAccessor._mapper_cls is TestMapper

    def test_intermediate_generic_no_mapper_cls(self):
        """Verify intermediate generic classes don't have _mapper_cls set."""

        class GenericAccessor[DataSourceT, MapperT: Mapper](
            AccessorBase[DataSourceT, MapperT],
        ):
            pass

        # _mapper_cls should NOT be set for intermediate generic classes
        assert not hasattr(GenericAccessor, "_mapper_cls")


class TestAccessorBaseDataSourceTypes:
    """Test AccessorBase with different data source types."""

    def test_xarray_dataset(self):
        """AccessorBase works with xr.Dataset."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        accessor = TestAccessor(ds)

        assert isinstance(accessor.data_source, xr.Dataset)
        assert accessor.data_source is ds

    def test_dict_data_source(self):
        """AccessorBase works with dict data source."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class DictMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

            def _read_value(self, data_source: dict[str, Any], name: str):
                return data_source[name]

        class DictAccessor(AccessorBase[dict[str, Any], DictMapper]):
            pass

        data = {"temp": 25.0, "pressure": 101.3}
        accessor = DictAccessor(data)

        assert isinstance(accessor.data_source, dict)
        assert accessor.data_source is data


class TestAccessorBaseValidation:
    """Test _validate() functionality."""

    def test_validation_called(self):
        """_validate() is called during initialization."""
        validate_called = []

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            def _validate(self):
                validate_called.append(True)

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        TestAccessor(ds)

        assert validate_called == [True]

    def test_validation_can_raise(self):
        """_validate() can raise ValueError for invalid data."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            def _validate(self):
                if "pressure" not in self.data_source:
                    msg = "Missing required 'pressure' variable"
                    raise ValueError(msg)

        ds_valid = xr.Dataset({"temp": ("x", [1, 2, 3]), "pressure": ("x", [1, 2, 3])})
        ds_invalid = xr.Dataset({"temp": ("x", [1, 2, 3])})

        # Should work with valid data
        accessor = TestAccessor(ds_valid)
        assert accessor.data_source is ds_valid

        # Should raise with invalid data
        with pytest.raises(ValueError, match="Missing required 'pressure' variable"):
            TestAccessor(ds_invalid)

    def test_no_validation_by_default(self):
        """Base _validate() does nothing (no-op)."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass  # No _validate override

        # Should work even with minimal data
        ds = xr.Dataset()
        accessor = TestAccessor(ds)
        assert accessor.data_source is ds


class TestAccessorBaseProperties:
    """Test AccessorBase property accessors."""

    def test_mapper_property(self):
        """mapper property returns the mapper instance."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        accessor = TestAccessor(ds)

        assert isinstance(accessor.mapper, TestMapper)
        assert accessor.mapper.schema.temp in accessor.mapper

    def test_data_source_property(self):
        """data_source property returns the data source."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        accessor = TestAccessor(ds)

        assert accessor.data_source is ds


class TestAccessorBaseAsXarrayAccessor:
    """Test AccessorBase used as xarray accessor."""

    def test_xarray_accessor_pattern(self):
        """AccessorBase can be used as xarray accessor."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        @xr.register_dataset_accessor("test_acc")
        class TestAccessor(AccessorBase[xr.Dataset, TestMapper]):
            def get_temp(self):
                return self.mapper.get_arr(self.data_source, self.mapper.schema.temp)

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})

        # Should be accessible via .test_acc
        assert hasattr(ds, "test_acc")
        assert isinstance(ds.test_acc, TestAccessor)
        assert (ds.test_acc.get_temp() == ds["temp"]).all()

        # Clean up accessor registration
        del xr.Dataset.test_acc  # type: ignore[attr-defined]


class TestAccessorBaseAsView:
    """Test AccessorBase used as data view."""

    def test_view_pattern_with_mapper(self):
        """AccessorBase can be used as view accepting mapper."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestView(AccessorBase[xr.Dataset, TestMapper]):
            def _validate(self):
                # View-specific validation
                if "temp" not in self.data_source:
                    msg = "View requires 'temp' variable"
                    raise ValueError(msg)

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        mapper = TestMapper.from_data_source(ds)

        # Create view with pre-existing mapper
        view = TestView(ds, mapper)
        assert view.mapper is mapper
        assert view.data_source is ds

    def test_view_pattern_auto_mapper(self):
        """AccessorBase can be used as view with auto-created mapper."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class TestView(AccessorBase[xr.Dataset, TestMapper]):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})

        # Create view without mapper - should auto-create
        view = TestView(ds)
        assert isinstance(view.mapper, TestMapper)
        assert view.data_source is ds


class TestAccessorBaseErrorCases:
    """Test error handling in AccessorBase."""

    def test_no_mapper_class_detected(self):
        """Error if no mapper class detected and no mapper provided."""

        # Create intermediate generic class
        class GenericAccessor[DataSourceT, MapperT: Mapper](
            AccessorBase[DataSourceT, MapperT],
        ):
            pass

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})

        # Should raise AttributeError because no _mapper_cls set
        with pytest.raises(
            AttributeError,
            match="_mapper_cls",
        ):
            GenericAccessor(ds)


class TestAccessorBaseInheritance:
    """Test inheritance patterns with AccessorBase."""

    def test_multiple_inheritance_levels(self):
        """AccessorBase works with multiple inheritance levels."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        # Base accessor
        class BaseAccessor(AccessorBase[xr.Dataset, TestMapper]):
            def base_method(self):
                return "base"

        # Derived accessor
        class DerivedAccessor(BaseAccessor):
            def derived_method(self):
                return "derived"

        ds = xr.Dataset({"temp": ("x", [1, 2, 3])})
        accessor = DerivedAccessor(ds)

        assert accessor.base_method() == "base"
        assert accessor.derived_method() == "derived"
        assert isinstance(accessor.mapper, TestMapper)

    def test_override_validate_in_subclass(self):
        """Subclass can override _validate()."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(XarrayMapper[TestSchema]):
            pass

        class BaseAccessor(AccessorBase[xr.Dataset, TestMapper]):
            pass

        class StrictAccessor(BaseAccessor):
            def _validate(self):
                if len(self.data_source.data_vars) < 2:
                    msg = "Requires at least 2 variables"
                    raise ValueError(msg)

        ds_valid = xr.Dataset({"temp": ("x", [1, 2, 3]), "pressure": ("x", [1, 2, 3])})
        ds_invalid = xr.Dataset({"temp": ("x", [1, 2, 3])})

        # Base accessor should work with both
        BaseAccessor(ds_valid)
        BaseAccessor(ds_invalid)

        # Strict accessor should only work with valid
        StrictAccessor(ds_valid)
        with pytest.raises(ValueError, match="Requires at least 2 variables"):
            StrictAccessor(ds_invalid)
