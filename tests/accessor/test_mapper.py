"""Tests for Mapper base class functionality."""

from __future__ import annotations

import pytest
from pydantic.dataclasses import dataclass

from tollan.accessor.mapper import Mapper
from tollan.accessor.schema import (
    MISSING,
    FieldMapping,
    MappedField,
    MappedFieldSource,
    Mapping,
    Schema,
)


class MockMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mock mapper for testing abstract base."""

    data_source: dict[str, any]

    def _has_field(self, name: str) -> bool:
        return name in self.data_source

    def _read_value(self, name: str):
        return self.data_source[name]


class TestMapperCreation:
    """Test Mapper creation and initialization."""

    def test_with_schema(self):
        """Create mapper with explicit schema."""
        data = {"temp": 25.0, "pressure": 101.3}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)

        assert mapper.data_source is data
        assert isinstance(mapper.schema, TestSchema)
        assert len(mapper.mapped_fields) > 0

    def test_with_default_schema(self):
        """Create mapper with explicit empty Schema."""
        data = {"field": 123}

        @dataclass
        class EmptySchema(Schema):
            pass

        class TestMapper(MockMapper[EmptySchema]):
            pass

        mapper = TestMapper(data_source=data)

        assert mapper.data_source == data
        assert isinstance(mapper.schema, Schema)
        assert len(mapper.mapped_fields) == 0


class TestFieldResolution:
    """Test field resolution logic."""

    def test_resolve_field_found(self):
        """Resolve field that exists."""
        data = {"temperature": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temperature"
        assert mapped_field.source == MappedFieldSource.DATA_SOURCE
        assert mapped_field.field_mapping.names == ("temperature",)

    def test_resolve_field_alternative(self):
        """Resolve field using alternative name."""
        data = {"temp_c": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping(("temperature", "temp_c", "T"))

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temp_c"

    def test_resolve_field_missing_required(self):
        """Missing required field raises error."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature", required=True)

        class TestMapper(MockMapper[TestSchema]):
            pass

        with pytest.raises(KeyError, match="Required field not found"):
            TestMapper(data_source=data)

    def test_resolve_field_missing_optional(self):
        """Missing optional field marked as MISSING."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature", required=False)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == ""
        assert mapped_field.value is MISSING
        assert mapped_field.source == MappedFieldSource.MISSING


class TestValueRetrieval:
    """Test value retrieval methods."""

    def test_get_value_lazy(self):
        """Get value lazily (default)."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp", resolve_value=False)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        value = mapper.get_value(mapper.schema.temp)

        assert value == 25.0

    def test_get_value_eager(self):
        """Get value eagerly (immediate resolution)."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp", resolve_value=True)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        # Value should be loaded during resolution
        assert mapped_field.value == 25.0

    def test_get_value_missing(self):
        """Get value for missing field raises KeyError."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp", required=False)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(mapper.schema.temp)

    def test_get_value_with_empty_schema(self):
        """Get value still works with empty schema via direct access."""
        data = {"temperature": 25.0, "pressure": 101.3}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)

        value = mapper.get_value(mapper.schema.temp)
        assert value == 25.0


class TestMappedFields:
    """Test MappedField tracking."""

    def test_mapped_fields_property(self):
        """mapped_fields property returns dict."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_fields = mapper.mapped_fields

        assert isinstance(mapped_fields, dict)
        assert len(mapped_fields) == 1
        assert mapper.schema.temp in mapped_fields

    def test_mapped_field_has_schema_path(self):
        """MappedField includes schema path."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.schema_path == "TestSchema.temp"


class TestConditionalMapping:
    """Test conditional mapping resolution."""

    @pytest.mark.skip(
        reason="Pydantic limitation with local class ConditionalMapping __init__"
    )
    def test_custom_mapping_base(self):
        """Custom Mapping subclass with conditional logic."""

        # Subclass Mapping and override resolve() for conditional behavior
        class ConditionalMapping(Mapping):
            def __init__(self, celsius_name: str, fahrenheit_name: str):
                # Store in names tuple for lookup
                super().__init__((celsius_name, fahrenheit_name))
                self._celsius = celsius_name
                self._fahrenheit = fahrenheit_name

            def resolve(self, context) -> FieldMapping:
                # Check if fahrenheit version exists, otherwise fall back to celsius
                if context._has_field(self._fahrenheit):
                    return FieldMapping(self._fahrenheit)
                return FieldMapping(self._celsius)

        data = {"temp_c": 25.0, "temp_f": 77.0}

        @dataclass
        class TestSchema(Schema):
            temp: ConditionalMapping = ConditionalMapping("temp_c", "temp_f")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper(data_source=data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        # Should resolve to fahrenheit since it exists
        assert mapped_field.name == "temp_f"
