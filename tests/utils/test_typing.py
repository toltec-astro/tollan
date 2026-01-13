"""Tests for tollan.utils.typing module."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

import astropy.units as u
import pytest
from pydantic import BaseModel

from tollan.utils.typing import ensure_cls_attr_from_type_args, get_typing_args


class TestGetTypingArgs:
    """Test get_typing_args function."""

    def test_annotated_types(self):
        """Test extracting args from Annotated types."""
        T1 = Annotated[list, list[int], type[dict[str, dict]]]

        result = get_typing_args(T1)
        # get_typing_args recursively extracts types
        assert list in result
        assert int in result
        # Note: dict[str, dict] is kept as-is (not fully recursed)

    def test_annotated_with_classes(self):
        """Test extracting args from Annotated with class types."""

        class D(dict[str, dict]):
            pass

        T2 = Annotated[list, list[int], D]
        result = get_typing_args(T2)
        # Recursively extracts leaf types
        assert list in result
        assert int in result
        assert D in result

    def test_max_depth_none(self):
        """Test recursive extraction with max_depth=None."""
        T1 = Annotated[list, list[int], type[dict[str, dict]]]

        result = get_typing_args(T1, max_depth=None)
        assert set(result) == {list, int, str, dict}

    def test_class_inheritance(self):
        """Test extracting from class inheritance chain."""

        class D(dict[str, dict]):
            pass

        class E(D):
            pass

        class F(E):
            pass

        # Should extract generic args from base classes
        result_d = get_typing_args(D, max_depth=None)
        assert str in result_d and dict in result_d

        result_e = get_typing_args(E, max_depth=1)
        assert str in result_e and dict in result_e

        result_f = get_typing_args(F, max_depth=1)
        assert str in result_f and dict in result_f

    def test_no_args(self):
        """Test classes with no type arguments."""
        assert get_typing_args(int, max_depth=None) == []
        assert get_typing_args(str) == []

        class Plain:
            pass

        assert get_typing_args(Plain) == []

    def test_generic_with_typevar(self):
        """Test Generic classes with TypeVar."""
        T = TypeVar("T")

        class Container(Generic[T]):
            pass

        class StringContainer(Container[str]):
            pass

        result = get_typing_args(StringContainer)
        assert str in result

    def test_bound_filter(self):
        """Test filtering by bound type."""

        class Base:
            pass

        class Derived(Base):
            pass

        class Other:
            pass

        T = Annotated[list, Derived, Other]

        # Filter by bound=Base (should include Derived but not Other)
        result = get_typing_args(T, bound=Base)
        assert Derived in result
        assert Other not in result

    def test_type_filter(self):
        """Test filtering by type (instance check)."""
        # type_filter uses isinstance, so it filters values not types
        # For filtering types themselves, use bound parameter
        # Note: First item can be ForwardRef if it looks like a type name
        T = Annotated[list, "world", 123, 456.0]

        # Filter to only string instances
        result = get_typing_args(T, type_filter=str)
        assert result == ["world"]

        # Filter to only int instances
        result_int = get_typing_args(T, type_filter=int)
        assert result_int == [123]

    def test_unique_flag(self):
        """Test unique flag expects exactly one result."""
        # unique=True expects exactly one result
        # Must use with bound or type_filter to get unique result

        class MyModel(BaseModel):
            x: int = 1

        T = TypeVar("T")

        class Handler(Generic[T]):
            pass

        class MyHandler(Handler[MyModel]):
            pass

        result_unique = get_typing_args(MyHandler, bound=BaseModel, unique=True)
        assert result_unique == MyModel

        # Multiple results should raise
        class Model2(BaseModel):
            y: str = "test"

        T2 = Annotated[MyModel, Model2]
        with pytest.raises(ValueError, match="Expected exactly one"):
            get_typing_args(T2, bound=BaseModel, unique=True)

    def test_literal_extraction(self):
        """Test extracting values from Literal types."""
        T = Literal["value1", "value2"]

        # get_typing_args extracts the literal values
        result = get_typing_args(T)
        assert "value1" in result
        assert "value2" in result

    def test_complex_nested_generics(self):
        """Test complex nested generic structures."""

        T = TypeVar("T")

        class Base(Generic[T]):
            pass

        class Middle(Base[list[str]]):
            pass

        class Final(Middle):
            pass

        result = get_typing_args(Final, max_depth=3)
        # Extracts leaf type from the generic chain
        assert str in result

    def test_pydantic_model_extraction(self):
        """Test extracting Pydantic model from Generic."""

        class MyModel(BaseModel):
            x: int = 1

        T = TypeVar("T")

        class Handler(Generic[T]):
            pass

        class ConcreteHandler(Handler[MyModel]):
            pass

        result = get_typing_args(ConcreteHandler, bound=BaseModel)
        assert result == [MyModel]

    def test_multiple_type_params(self):
        """Test Generic with multiple type parameters."""
        T = TypeVar("T")
        U = TypeVar("U")

        class Pair(Generic[T, U]):
            pass

        class StrIntPair(Pair[str, int]):
            pass

        result = get_typing_args(StrIntPair)
        assert str in result
        assert int in result

    def test_generic_base_with_typevar_unique(self):
        """Test that generic base classes with TypeVars return None."""
        T = TypeVar("T")

        class GenericBase(Generic[T]):
            pass

        # TypeVars are filtered out, so generic base returns None with unique=True
        result = get_typing_args(GenericBase, unique=True)
        assert result is None

    def test_concrete_class_unique(self):
        """Test that concrete classes with bound filter
        return the type when unique=True."""

        class Base:
            pass

        class Concrete(Base):
            pass

        T = TypeVar("T", bound=Base)

        class GenericContainer(Generic[T]):
            pass

        class ConcreteContainer(GenericContainer[Concrete]):
            pass

        # Concrete instantiation should return the concrete type
        result = get_typing_args(ConcreteContainer, bound=Base, unique=True)
        assert result is Concrete

    def test_generic_base_with_bound_unique(self):
        """Test generic base with bound filter returns None."""

        class Base:
            pass

        T = TypeVar("T", bound=Base)

        class GenericContainer(Generic[T]):
            pass

        # TypeVar T is not a concrete subclass of Base
        # With bound filter, TypeVar gets filtered out → 0 results
        # With TypeVar present in raw args, should return None (not raise)
        result = get_typing_args(GenericContainer, bound=Base, unique=True)
        assert result is None

    def test_concrete_missing_type_raises(self):
        """Test that concrete class without type param
        raises ValueError with unique=True."""

        class Base:
            pass

        # Plain class with no type parameters
        class PlainClass:
            pass

        # Should raise ValueError - no TypeVars, 0 results with bound filter
        with pytest.raises(ValueError, match="Expected exactly one"):
            get_typing_args(PlainClass, bound=Base, unique=True)

    def test_typevar_detection_with_nested_generics(self):
        """Test TypeVar detection in nested generic hierarchies."""

        class Base:
            pass

        class Concrete(Base):
            pass

        T = TypeVar("T", bound=Base)

        class Level1(Generic[T]):
            pass

        class Level2(Level1[T]):
            pass

        class Level3(Level2[Concrete]):
            pass

        # Level1 and Level2 are generic (have TypeVar) → None
        assert get_typing_args(Level1, bound=Base, unique=True) is None
        assert get_typing_args(Level2, bound=Base, unique=True) is None

        # Level3 is concrete (no TypeVar, has Concrete) → Concrete
        assert get_typing_args(Level3, bound=Base, unique=True) is Concrete

    def test_multiple_bounds_with_typevar(self):
        """Test that multiple concrete types raise error even with unique=True."""

        class Base:
            pass

        class Type1(Base):
            pass

        class Type2(Base):
            pass

        T = TypeVar("T")
        U = TypeVar("U")

        class MultiParam(Generic[T, U]):
            pass

        class ConcreteMulti(MultiParam[Type1, Type2]):
            pass

        # Multiple concrete types matching bound should still raise
        with pytest.raises(ValueError, match="Expected exactly one"):
            get_typing_args(ConcreteMulti, bound=Base, unique=True)

    def test_typevar_without_unique(self):
        """Test that TypeVars are always filtered out, regardless of unique flag."""
        T = TypeVar("T")

        class GenericBase(Generic[T]):
            pass

        # Without unique=True, should return empty list (TypeVars filtered out)
        result = get_typing_args(GenericBase, unique=False)
        assert result == []

        # With bound filter that excludes TypeVar, should return empty list
        class Base:
            pass

        result = get_typing_args(GenericBase, bound=Base, unique=False)
        assert result == []


class TestQuantityPhysicalType:
    """Test physical type extraction from Quantity types."""

    def test_unit_physical_type(self):
        """Test extraction from unit-based Quantity."""
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        Q1 = u.Quantity[u.m]
        assert get_physical_type_from_quantity_type(Q1) == "length"

        Q2 = u.Quantity[u.s]
        assert get_physical_type_from_quantity_type(Q2) == "time"

    def test_string_physical_type(self):
        """Test extraction from string-based Quantity."""
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        Q1 = u.Quantity["length"]
        assert get_physical_type_from_quantity_type(Q1) == "length"

        Q2 = u.Quantity["time"]
        assert get_physical_type_from_quantity_type(Q2) == "time"

    def test_derived_units(self):
        """Test with derived units."""
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        Q1 = u.Quantity[u.m / u.s]
        assert get_physical_type_from_quantity_type(Q1) == "speed"

        Q2 = u.Quantity[u.kg * u.m / u.s**2]
        assert get_physical_type_from_quantity_type(Q2) == "force"

    def test_invalid_quantity_type(self):
        """Test with invalid quantity type."""
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        # Should return None for non-Quantity types (no error raised)
        assert get_physical_type_from_quantity_type(int) is None
        assert get_physical_type_from_quantity_type(str) is None


class TestTypingUtilsEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_annotated(self):
        """Test Annotated with no metadata."""
        # This might not be valid, but test handling
        result = get_typing_args(list)
        assert isinstance(result, list)

    def test_deeply_nested(self):
        """Test deeply nested type structures."""
        T = Annotated[
            dict[str, list[tuple[int, str]]],
            list[dict[str, int]],
        ]

        result = get_typing_args(T, max_depth=5)
        # Should extract leaf types from deep nesting
        assert len(result) >= 5
        assert str in result
        assert int in result

    def test_max_depth_zero(self):
        """Test max_depth=0 stops recursion immediately."""
        T = Annotated[list[int], dict[str, str]]

        result = get_typing_args(T, max_depth=0)
        # Should only get top-level types
        assert len(result) == 2

    def test_circular_reference_safety(self):
        """Test handling of circular references in type hierarchy."""

        # This is tricky to set up, but the function should handle it
        class A:
            pass

        class B(A):
            pass

        # Try to extract with reasonable max_depth
        result = get_typing_args(B, max_depth=10)
        assert isinstance(result, list)


class TestEnsureClsAttrFromTypeArgs:
    """Test ensure_cls_attr_from_type_args function."""

    def test_basic_inference(self):
        """Test basic attribute inference from Generic parameter."""

        class MyModel(BaseModel):
            value: str = "test"

        T = TypeVar("T")

        class Handler(Generic[T]):
            config_model: type | None = None

        class MyHandler(Handler[MyModel]):
            pass

        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
        )

        assert MyHandler.config_model is MyModel

    def test_skip_on_exist_true(self):
        """Test that skip_on_exist=True preserves existing values."""

        class Model1(BaseModel):
            x: int = 1

        class Model2(BaseModel):
            y: str = "test"

        T = TypeVar("T")

        class Handler(Generic[T]):
            config_model: type | None = None

        class MyHandler(Handler[Model1]):
            config_model = Model2  # Explicit override

        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
            skip_on_exist=True,
            disallow_explicit=False,  # Allow explicit for this test
        )

        # Should keep the explicit value
        assert MyHandler.config_model is Model2

    def test_skip_on_exist_false(self):
        """Test that skip_on_exist=False overwrites existing values."""

        class Model1(BaseModel):
            x: int = 1

        class Model2(BaseModel):
            y: str = "test"

        T = TypeVar("T")

        class Handler(Generic[T]):
            config_model: type | None = None

        class MyHandler(Handler[Model1]):
            config_model = Model2  # Explicit override

        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
            skip_on_exist=False,
            disallow_explicit=False,  # Allow explicit for this test
        )

        # Should infer from type parameter and overwrite
        assert MyHandler.config_model is Model1

    def test_no_type_args_with_default_skip_on_exist(self):
        """Test behavior when no type args found but default exists
        with skip_on_exist=True."""

        class Handler:
            config_model: type | None = None

        class MyHandler(Handler):
            config_model = str  # Has default

        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
            skip_on_exist=True,  # Skip because default exists
            disallow_explicit=False,  # Allow explicit for this test
        )

        # Should keep default since no valid type args found and skip_on_exist=True
        assert MyHandler.config_model is str

    def test_intermediate_generic_class_graceful(self):
        """Test that intermediate generic classes (with TypeVars) don't raise errors."""

        T = TypeVar("T")

        class GenericHandler(Generic[T]):
            pass

        # Should not raise - intermediate generic class
        # Returns without setting attribute because no concrete type
        ensure_cls_attr_from_type_args(
            GenericHandler,
            "mapper_cls",
            bound=BaseModel,
            disallow_explicit=False,
        )

        # Should not have set the attribute (no concrete type)
        assert not hasattr(GenericHandler, "mapper_cls")

    def test_intermediate_generic_subclass_graceful(self):
        """Test that intermediate generic subclasses work correctly."""

        class Base:
            pass

        T = TypeVar("T", bound=Base)

        class Level1(Generic[T]):
            pass

        class Level2(Level1[T]):
            pass

        # Level1 and Level2 are both generic (have TypeVars) - should not raise
        ensure_cls_attr_from_type_args(
            Level1,
            "mapper_cls",
            bound=Base,
            disallow_explicit=False,
        )
        assert not hasattr(Level1, "mapper_cls")

        ensure_cls_attr_from_type_args(
            Level2,
            "mapper_cls",
            bound=Base,
            disallow_explicit=False,
        )
        assert not hasattr(Level2, "mapper_cls")

    def test_concrete_class_after_generic_sets_attr(self):
        """Test that concrete class after generic chain sets attribute correctly."""

        class MyModel(BaseModel):
            value: str = "test"

        T = TypeVar("T")

        class GenericHandler(Generic[T]):
            pass

        class ConcreteHandler(GenericHandler[MyModel]):
            mapper_cls: type

        # GenericHandler should not set attribute (generic with TypeVar)
        ensure_cls_attr_from_type_args(
            GenericHandler,
            "mapper_cls",
            bound=BaseModel,
            disallow_explicit=False,
        )
        assert not hasattr(GenericHandler, "mapper_cls")

        # ConcreteHandler should set attribute (concrete type)
        ensure_cls_attr_from_type_args(
            ConcreteHandler,
            "mapper_cls",
            bound=BaseModel,
            disallow_explicit=False,
        )
        assert ConcreteHandler.mapper_cls is MyModel

    def test_multiple_type_args_raises(self):
        """Test that multiple matching type args raises ValueError."""

        class Model1(BaseModel):
            x: int = 1

        class Model2(BaseModel):
            y: str = "test"

        T = TypeVar("T")
        U = TypeVar("U")

        class Handler(Generic[T, U]):
            config_model: type | None = None

        class MyHandler(Handler[Model1, Model2]):
            pass

        with pytest.raises(ValueError, match="Expected exactly one typing arg"):
            ensure_cls_attr_from_type_args(
                MyHandler,
                "config_model",
                bound=BaseModel,
            )

    def test_no_type_args_no_default_raises(self):
        """Test that no type args and no default raises ValueError."""

        class Handler:
            pass

        class MyHandler(Handler):
            pass

        with pytest.raises(ValueError, match="Expected exactly one typing arg"):
            ensure_cls_attr_from_type_args(
                MyHandler,
                "config_model",
                bound=BaseModel,
            )

    def test_max_depth_parameter(self):
        """Test max_depth parameter controls recursion depth."""

        class MyModel(BaseModel):
            value: str = "test"

        T = TypeVar("T")

        class BaseHandler(Generic[T]):
            pass

        class MiddleHandler(BaseHandler[MyModel]):
            pass

        class MyHandler(MiddleHandler):
            config_model: type | None = None

        # With max_depth=2, should find MyModel through MiddleHandler
        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            max_depth=2,
            bound=BaseModel,
            disallow_explicit=False,  # Allow explicit for this test
        )

        assert MyHandler.config_model is MyModel

    def test_type_filter_parameter(self):
        """Test using type_filter instead of bound."""

        T = TypeVar("T")

        class Container(Generic[T]):
            content_type: type | None = None

        class StrContainer(Container[str]):
            pass

        ensure_cls_attr_from_type_args(
            StrContainer,
            "content_type",
            type_filter=type,
        )

        assert StrContainer.content_type is str

    def test_with_literal_types(self):
        """Test inference with Literal types."""
        T = TypeVar("T")

        class Handler(Generic[T]):
            key: str | None = None

        # Create a handler with Literal type parameter
        class MyHandler(Handler[Literal["my_key"]]):
            pass

        ensure_cls_attr_from_type_args(
            MyHandler,
            "key",
            type_filter=str,
        )

        assert MyHandler.key == "my_key"

    def test_inherited_attribute(self):
        """Test behavior with inherited attributes."""

        class Model1(BaseModel):
            x: int = 1

        class Model2(BaseModel):
            y: str = "test"

        T = TypeVar("T")

        class BaseHandler(Generic[T]):
            config_model: type | None = None

        class MiddleHandler(BaseHandler[Model1]):
            pass

        # Initialize the base handler's attribute
        ensure_cls_attr_from_type_args(
            MiddleHandler,
            "config_model",
            bound=BaseModel,
        )

        assert MiddleHandler.config_model is Model1

        # Now create a subclass with different type parameter
        class DerivedHandler(MiddleHandler, Generic[T]):
            pass

        class MyHandler(DerivedHandler[Model2]):
            pass

        # With skip_on_exist=True (default), should keep inherited value
        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
            skip_on_exist=True,
        )

        assert MyHandler.config_model is Model1

    def test_sets_attribute_on_class(self):
        """Test that attribute is set on the class, not instance."""

        class MyModel(BaseModel):
            value: str = "test"

        T = TypeVar("T")

        class Handler(Generic[T]):
            pass

        class MyHandler(Handler[MyModel]):
            config_model: type

        # Should not have attribute before
        assert not hasattr(MyHandler, "config_model")

        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
        )

        # Should have attribute after
        assert hasattr(MyHandler, "config_model")
        assert MyHandler.config_model is MyModel

    def test_disallow_explicit_parameter(self):
        """Test that disallow_explicit=True raises TypeError for explicit attributes."""

        class MyModel(BaseModel):
            value: str = "test"

        class OtherModel(BaseModel):
            value: int = 1

        T = TypeVar("T")

        class Handler(Generic[T]):
            pass

        class MyHandler(Handler[MyModel]):
            config_model = OtherModel  # Explicitly set

        # Should raise TypeError when disallow_explicit=True
        with pytest.raises(TypeError, match="explicitly sets 'config_model'"):
            ensure_cls_attr_from_type_args(
                MyHandler,
                "config_model",
                bound=BaseModel,
                disallow_explicit=True,
            )

    def test_disallow_explicit_allows_inherited(self):
        """Test that disallow_explicit=True allows inherited attributes."""

        class MyModel(BaseModel):
            value: str = "test"

        class OtherModel(BaseModel):
            value: int = 1

        T = TypeVar("T")

        class Handler(Generic[T]):
            config_model = OtherModel  # Set on base class

        class MyHandler(Handler[MyModel]):
            pass  # Inherits config_model, doesn't set it explicitly

        # Should not raise - attribute is inherited, not explicitly set
        ensure_cls_attr_from_type_args(
            MyHandler,
            "config_model",
            bound=BaseModel,
            skip_on_exist=False,
            disallow_explicit=True,
        )

        # Should infer from type parameter
        assert MyHandler.config_model is MyModel
