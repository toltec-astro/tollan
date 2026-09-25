"""Tests for schema and mapping value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from typing import Any

import pytest

from tollan.accessor.schema import (
    MISSING,
    MappedField,
    MappedFieldSource,
    Mapping,
    MappingContext,
    NameMapping,
    Schema,
)


class TestNameMapping:
    """Test the concrete ordered-name mapping."""

    def test_single_name_string(self):
        """Single name string is converted to tuple."""
        fm = NameMapping("temperature")
        assert fm.names == ("temperature",)
        assert fm.resolve_value is False

    def test_single_name_tuple(self):
        """Single name tuple."""
        fm = NameMapping(("temperature",))
        assert fm.names == ("temperature",)

    def test_multiple_names(self):
        """Multiple alternative names."""
        fm = NameMapping(("temp", "temperature", "T"))
        assert fm.names == ("temp", "temperature", "T")

    def test_list_converted_to_tuple(self):
        """List is converted to tuple."""
        fm = NameMapping(["temp", "temperature"])
        assert fm.names == ("temp", "temperature")
        assert isinstance(fm.names, tuple)

    def test_immediate_resolve(self):
        """Field marked for immediate value resolution."""
        fm = NameMapping("field", resolve_value=True)
        assert fm.resolve_value is True

    def test_all_parameters(self):
        """All parameters specified."""
        fm = NameMapping(("alt1", "alt2"), resolve_value=True)
        assert fm.names == ("alt1", "alt2")
        assert fm.resolve_value is True

    def test_frozen(self):
        """Mapping is immutable."""
        from pydantic_core import ValidationError

        fm = NameMapping("field")
        with pytest.raises(
            (AttributeError, ValidationError, TypeError),
        ):  # FrozenInstanceError
            fm.names = ("other",)  # ty: ignore[invalid-assignment]

    def test_invalid_names_type(self):
        """Invalid names type raises error."""
        with pytest.raises(ValueError, match="name or a sequence"):
            NameMapping(123)  # ty: ignore[invalid-argument-type]

    def test_invalid_names_elements(self):
        """Non-string elements in names raises error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # Validation error
            NameMapping([1, 2, 3])  # ty: ignore[invalid-argument-type]

    def test_rejects_empty_names(self):
        """At least one physical name is required."""
        with pytest.raises(ValueError, match="at least one"):
            NameMapping(())

    def test_rejects_duplicate_names(self):
        """Repeated candidates cannot affect resolution and are rejected."""
        with pytest.raises(ValueError, match="unique"):
            NameMapping(("field", "field"))


class TestMapping:
    """Test the public mapping strategy contract."""

    def test_is_mapping(self):
        """Mapping is a Mapping."""
        m = NameMapping("field")
        assert isinstance(m, Mapping)

    def test_basic_creation(self):
        """Basic Mapping creation."""
        m = NameMapping("field")
        assert m.names == ("field",)
        assert m.resolve_value is False

    def test_with_kwargs(self):
        """Mapping with keyword arguments."""
        m = NameMapping("field", resolve_value=True)
        assert m.names == ("field",)
        assert m.resolve_value is True

    def test_resolve_returns_self(self):
        """resolve() returns self."""
        m = NameMapping("field")
        resolved = m.resolve(MappingContext(None, Schema(), {}))
        assert resolved is m
        assert isinstance(resolved, Mapping)

    def test_subclass_can_override_resolve(self):
        """Subclass can override resolve() for conditional mapping."""

        class ConditionalMapping(Mapping):
            def resolve(self, context: Any) -> NameMapping:
                # Return different Mapping based on context
                if hasattr(context, "use_fahrenheit") and context.use_fahrenheit:
                    return NameMapping("temp_f")
                return NameMapping("temp_c")

        mapping = ConditionalMapping()

        # Mock context
        class Context:
            use_fahrenheit = False

        ctx = Context()
        resolved = mapping.resolve(ctx)
        assert resolved.names == ("temp_c",)

        ctx.use_fahrenheit = True
        resolved = mapping.resolve(ctx)
        assert resolved.names == ("temp_f",)

    def test_unimplemented_resolve(self):
        """A strategy must implement resolve()."""

        class IncompleteMapping(Mapping):
            pass

        m = IncompleteMapping()
        with pytest.raises(NotImplementedError):
            m.resolve(MappingContext(None, Schema(), {}))

    def test_custom_mapping(self):
        """Custom mapping implementation."""

        class CustomMapping(Mapping):
            def __init__(self, primary: str, fallback: str) -> None:
                self.primary = primary
                self.fallback = fallback

            def resolve(self, context: Any) -> NameMapping:
                if hasattr(context, "data_source"):
                    if self.primary in context.data_source:
                        return NameMapping(self.primary)
                    return NameMapping(self.fallback)
                return NameMapping(self.primary)

        mapping = CustomMapping("preferred_name", "alternative_name")

        # Mock context
        class Context:
            def __init__(self) -> None:
                self.data_source = {"alternative_name": 123}

        resolved = mapping.resolve(Context())
        assert resolved.names == ("alternative_name",)


class TestMappingContext:
    """Test the short-lived mapping resolution context."""

    def test_frozen(self):
        """Resolution inputs cannot be rebound by a strategy."""
        schema = Schema()
        context = MappingContext({}, schema, {})
        with pytest.raises(FrozenInstanceError):
            context.data_source = {"other": 1}  # ty: ignore[invalid-assignment]


class TestMappedField:
    """Test MappedField result dataclass."""

    def test_basic_creation(self):
        """Basic MappedField creation."""
        fm = NameMapping("temp")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="temperature",
            value=25.0,
        )
        assert mf.mapping is fm
        assert mf.mapping_resolved is fm
        assert mf.name == "temperature"
        assert mf.value == 25.0
        assert mf.value_default is MISSING
        assert mf.source == MappedFieldSource.data_source

    def test_with_missing_value(self):
        """MappedField with MISSING value."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="",
            value=MISSING,
            source=MappedFieldSource.missing,
        )
        assert mf.value is MISSING
        assert mf.source == MappedFieldSource.missing

    def test_with_default_value(self):
        """MappedField with default value."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="",
            value_default=0.0,
            source=MappedFieldSource.default,
        )
        assert mf.value is MISSING
        assert mf.value_default == 0.0
        assert mf.source == MappedFieldSource.default

    def test_with_schema_path(self):
        """MappedField with schema path."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
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
            temp: Mapping = NameMapping("temperature")
            pressure: Mapping = NameMapping("pressure")

        schema = TestSchema()
        assert isinstance(schema.temp, NameMapping)
        assert isinstance(schema.pressure, NameMapping)
        assert isinstance(schema.temp, Mapping)
        assert isinstance(schema.pressure, Mapping)
        assert schema.temp.names == ("temperature",)

    def test_schema_with_alternatives(self):
        """Schema with alternative field names."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping(("temp_c", "temperature", "T"))

        schema = TestSchema()
        assert isinstance(schema.temp, NameMapping)
        assert schema.temp.names == ("temp_c", "temperature", "T")

    def test_get_schema_path(self):
        """get_schema_path() builds dotted path."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temperature")

        path = TestSchema.get_schema_path("temp")
        assert path == "TestSchema.temp"


class TestMappedFieldSource:
    """Test MappedFieldSource enum."""

    def test_enum_values(self):
        """Enum has correct values."""
        assert {
            name: member.value for name, member in MappedFieldSource.__members__.items()
        } == {
            "data_source": "data_source",
            "default": "default",
            "missing": "missing",
        }
        for member in MappedFieldSource:
            assert str(member) == member.value
            assert MappedFieldSource(member.value) is member

    def test_enum_distinct(self):
        """Enum values are distinct."""
        assert MappedFieldSource.data_source != MappedFieldSource.default
        assert MappedFieldSource.default != MappedFieldSource.missing


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
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="",
            value=MISSING,
        )
        assert mf.value is MISSING
