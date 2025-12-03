"""Tests for schema components: Mapping, MappingBase, Schema."""

# NOTE: Pylance type checking errors in this file are expected.
# Pydantic dataclasses generate __init__ from field annotations and don't
# respect TYPE_CHECKING overloads. The code works correctly at runtime
# because Pydantic's field_validator handles str/list -> tuple conversion.
# All tests pass successfully despite the type checking errors.

from __future__ import annotations

from typing import Any

import pytest
from pydantic.dataclasses import dataclass

from tollan.accessor.schema import (
    MISSING,
    MappedField,
    MappedFieldSource,
    Mapping,
    MappingBase,
    Schema,
)


class TestMappingDataclass:
    """Test Mapping dataclass."""

    def test_single_name_string(self):
        """Single name string is converted to tuple."""
        fm = Mapping("temperature")
        assert fm.names == ("temperature",)
        assert fm.required is True
        assert fm.resolve_value is False

    def test_single_name_tuple(self):
        """Single name tuple."""
        fm = Mapping(("temperature",))
        assert fm.names == ("temperature",)

    def test_multiple_names(self):
        """Multiple alternative names."""
        fm = Mapping(("temp", "temperature", "T"))
        assert fm.names == ("temp", "temperature", "T")

    def test_list_converted_to_tuple(self):
        """List is converted to tuple."""
        fm = Mapping(["temp", "temperature"])
        assert fm.names == ("temp", "temperature")
        assert isinstance(fm.names, tuple)

    def test_optional_field(self):
        """Optional field (not required)."""
        fm = Mapping("field", required=False)
        assert fm.required is False

    def test_immediate_resolve(self):
        """Field marked for immediate value resolution."""
        fm = Mapping("field", resolve_value=True)
        assert fm.resolve_value is True

    def test_all_parameters(self):
        """All parameters specified."""
        fm = Mapping(("alt1", "alt2"), required=False, resolve_value=True)
        assert fm.names == ("alt1", "alt2")
        assert fm.required is False
        assert fm.resolve_value is True

    def test_frozen(self):
        """Mapping is immutable."""
        from pydantic_core import ValidationError

        fm = Mapping("field")
        with pytest.raises(
            (AttributeError, ValidationError, TypeError),
        ):  # FrozenInstanceError
            fm.required = False  # type: ignore[misc]

    def test_invalid_names_type(self):
        """Invalid names type raises error."""
        with pytest.raises(ValueError, match="names must be str or tuple"):
            Mapping(123)  # type: ignore[arg-type]

    def test_invalid_names_elements(self):
        """Non-string elements in names raises error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # Validation error
            Mapping([1, 2, 3])  # type: ignore[arg-type]


class TestMapping:
    """Test Mapping class (Mapping + MappingBase)."""

    def test_is_mapping(self):
        """Mapping is a Mapping."""
        m = Mapping("field")
        assert isinstance(m, Mapping)
        assert isinstance(m, MappingBase)

    def test_basic_creation(self):
        """Basic Mapping creation."""
        m = Mapping("field")
        assert m.names == ("field",)
        assert m.required is True
        assert m.resolve_value is False

    def test_with_kwargs(self):
        """Mapping with keyword arguments."""
        m = Mapping("field", required=False, resolve_value=True)
        assert m.names == ("field",)
        assert m.required is False
        assert m.resolve_value is True

    def test_resolve_returns_self(self):
        """resolve() returns self."""
        m = Mapping("field")
        resolved = m.resolve(context=None)
        assert resolved is m
        assert isinstance(resolved, Mapping)

    def test_subclass_can_override_resolve(self):
        """Subclass can override resolve() for conditional mapping."""

        class ConditionalMapping(Mapping):
            def resolve(self, context: Any) -> Mapping:
                # Return different Mapping based on context
                if hasattr(context, "use_fahrenheit") and context.use_fahrenheit:
                    return Mapping("temp_f")
                return Mapping("temp_c")

        mapping = ConditionalMapping("temp")

        # Mock context
        class Context:
            use_fahrenheit = False

        ctx = Context()
        resolved = mapping.resolve(ctx)
        assert resolved.names == ("temp_c",)

        ctx.use_fahrenheit = True
        resolved = mapping.resolve(ctx)
        assert resolved.names == ("temp_f",)


class TestMappingBase:
    """Test MappingBase abstract class."""

    def test_abstract_resolve(self):
        """MappingBase requires resolve() implementation."""

        class IncompleteMapping(MappingBase):
            pass

        m = IncompleteMapping()
        with pytest.raises(NotImplementedError):
            m.resolve(None)

    def test_custom_mapping(self):
        """Custom mapping implementation."""

        class CustomMapping(MappingBase):
            def __init__(self, primary: str, fallback: str) -> None:
                self.primary = primary
                self.fallback = fallback

            def resolve(self, context: Any) -> Mapping:
                if hasattr(context, "data_source"):
                    if self.primary in context.data_source:
                        return Mapping(self.primary)
                    return Mapping(self.fallback)
                return Mapping(self.primary)

        mapping = CustomMapping("preferred_name", "alternative_name")

        # Mock context
        class Context:
            def __init__(self) -> None:
                self.data_source = {"alternative_name": 123}

        resolved = mapping.resolve(Context())
        assert resolved.names == ("alternative_name",)


class TestMappedField:
    """Test MappedField result dataclass."""

    def test_basic_creation(self):
        """Basic MappedField creation."""
        fm = Mapping("temp")
        mf = MappedField(mapping=fm, name="temperature", value=25.0)
        assert mf.mapping is fm
        assert mf.name == "temperature"
        assert mf.value == 25.0
        assert mf.source == MappedFieldSource.DATA_SOURCE

    def test_with_missing_value(self):
        """MappedField with MISSING value."""
        fm = Mapping("field")
        mf = MappedField(
            mapping=fm,
            name="",
            value=MISSING,
            source=MappedFieldSource.MISSING,
        )
        assert mf.value is MISSING
        assert mf.source == MappedFieldSource.MISSING

    def test_with_default_value(self):
        """MappedField with default value."""
        fm = Mapping("field", required=False)
        mf = MappedField(
            mapping=fm,
            name="",
            value=0.0,
            source=MappedFieldSource.DEFAULT,
        )
        assert mf.value == 0.0
        assert mf.source == MappedFieldSource.DEFAULT

    def test_with_schema_path(self):
        """MappedField with schema path."""
        fm = Mapping("field")
        mf = MappedField(
            mapping=fm,
            name="physical_field",
            value=123,
            schema_path="MySchema.field",
        )
        assert mf.schema_path == "MySchema.field"


class TestSchema:
    """Test Schema base class."""

    def test_basic_schema(self):
        """Basic schema definition."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")
            pressure: Mapping = Mapping("pressure", required=False)

        schema = TestSchema()
        assert isinstance(schema.temp, Mapping)
        assert isinstance(schema.pressure, Mapping)
        assert schema.temp.names == ("temperature",)
        assert schema.pressure.required is False

    def test_schema_with_alternatives(self):
        """Schema with alternative field names."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping(("temp_c", "temperature", "T"))

        schema = TestSchema()
        assert schema.temp.names == ("temp_c", "temperature", "T")

    def test_get_schema_path(self):
        """get_schema_path() builds dotted path."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        path = TestSchema.get_schema_path("temp")
        assert path == "TestSchema.temp"

    def test_get_schema_path_with_parent(self):
        """get_schema_path() with parent path."""

        @dataclass
        class TestSchema(Schema):
            field: Mapping = Mapping("value")

        path = TestSchema.get_schema_path("field", "ParentSchema.sub")
        assert path == "ParentSchema.sub.field"


class TestMappedFieldSource:
    """Test MappedFieldSource enum."""

    def test_enum_values(self):
        """Enum has correct values."""
        assert MappedFieldSource.DATA_SOURCE
        assert MappedFieldSource.DEFAULT
        assert MappedFieldSource.MISSING

    def test_enum_distinct(self):
        """Enum values are distinct."""
        assert MappedFieldSource.DATA_SOURCE != MappedFieldSource.DEFAULT
        assert MappedFieldSource.DEFAULT != MappedFieldSource.MISSING


class TestMissingSentinel:
    """Test MISSING sentinel value."""

    def test_missing_repr(self):
        """MISSING has readable repr."""
        assert repr(MISSING) == "MISSING"

    def test_missing_is_singleton(self):
        """MISSING is identity-comparable."""
        from tollan.accessor.schema import MISSING as MISSING2

        assert MISSING is MISSING2

    def test_missing_in_mapped_field(self):
        """MISSING can be used in MappedField."""
        fm = Mapping("field")
        mf = MappedField(mapping=fm, name="", value=MISSING)
        assert mf.value is MISSING
