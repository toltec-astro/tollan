"""Tests for Mapper base class functionality."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic.dataclasses import dataclass

from tollan.accessor.mapper import Mapper
from tollan.accessor.schema import (
    MISSING,
    MappedFieldSource,
    Mapping,
    MappingBase,
    Schema,
)


class MockMapper[SchemaT: Schema](Mapper[SchemaT]):
    """Mock mapper for testing abstract base."""

    def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
        return name in data_source

    def _read_value(self, data_source: dict[str, Any], name: str):
        return data_source[name]


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

        mapper = TestMapper.from_data_source(data)

        assert isinstance(mapper.schema, TestSchema)
        assert len(mapper.mapped_fields) > 0

    def test_with_empty_schema(self):
        """Create mapper with explicit empty Schema."""
        data = {"field": 123}

        @dataclass
        class EmptySchema(Schema):
            pass

        class TestMapper(MockMapper[EmptySchema]):
            pass

        mapper = TestMapper.from_data_source(data)

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

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temperature"
        assert mapped_field.source == MappedFieldSource.DATA_SOURCE
        assert mapped_field.mapping.names == ("temperature",)

    def test_resolve_field_alternative(self):
        """Resolve field using alternative name."""
        data = {"temp_c": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping(("temperature", "temp_c", "T"))

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temp_c"

    def test_resolve_field_missing_optional(self):
        """Missing field marked as MISSING."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == ""
        assert mapped_field.value is MISSING
        assert mapped_field.source == MappedFieldSource.MISSING


class TestValueRetrieval:
    """Test value retrieval methods."""

    def test_get_value_lazy(self):
        """Get value lazily (not loaded during resolution)."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp", resolve_value=False)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        # Value should NOT be loaded yet (lazy loading)
        assert mapped_field.value is MISSING

        # Now get the value - this triggers loading
        value = mapper.get_value(data, mapper.schema.temp)
        assert value == 25.0

    def test_get_value_eager(self):
        """Get value eagerly (immediate resolution)."""
        data = {"temp": 25.0}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp", resolve_value=True)

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        # Value should be loaded during resolution
        assert mapped_field.value == 25.0

    def test_get_value_missing(self):
        """Get value for missing field raises KeyError."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(data, mapper.schema.temp)


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

        mapper = TestMapper.from_data_source(data)
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

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.schema_path == "TestSchema.temp"


class TestConditionalMapping:
    """Test conditional mapping resolution."""

    def test_custom_mapping_base(self):
        """Custom MappingBase with conditional resolution based on schema state."""
        from pydantic import Field
        from pydantic.dataclasses import rebuild_dataclass

        # Conditional mapping that checks a "version" field
        @dataclass(frozen=True)
        class ConditionalDataMapping(MappingBase):
            root: ClassVar[dict[str, Mapping]] = {
                "v1": Mapping("data_v1"),
                "v2": Mapping("data_v2"),
            }

            def resolve(self, context: MockMapper) -> Mapping:
                # Check mapper.mapped_fields for previously resolved "version" field
                version_mapping = context.schema.version
                if version_mapping in context.mapped_fields:
                    version_field = context.mapped_fields[version_mapping]
                    if version_field.value == 2:
                        return self.root["v2"]
                return self.root["v1"]

        data = {"version": 2, "data_v1": "old", "data_v2": "new"}

        @dataclass
        class TestSchema(Schema):
            version: Mapping = Mapping(
                "version",
                resolve_value=True,
            )  # Resolve value immediately
            data: ConditionalDataMapping = Field(
                default_factory=ConditionalDataMapping,
            )

        # Rebuild to handle forward reference
        rebuild_dataclass(TestSchema)  # pyright: ignore[reportArgumentType]

        class TestMapper(MockMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)

        # Version should be resolved first
        assert mapper.mapped_fields[mapper.schema.version].value == 2

        # Data should resolve to v2 based on version
        data_field = mapper.mapped_fields[mapper.schema.data]
        assert data_field.name == "data_v2"
