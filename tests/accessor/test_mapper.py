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


class TestMapperCreation:
    """Test Mapper creation and initialization."""

    def test_with_schema(self):
        """Create mapper with explicit schema."""
        data = {"temp": 25.0, "pressure": 101.3}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(Mapper[TestSchema]):
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

        class TestMapper(Mapper[EmptySchema]):
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

        class TestMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

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

        class TestMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temp_c"

    def test_resolve_field_missing_optional(self):
        """Missing field marked as MISSING (default _has_field returns False)."""
        data = {}

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        class TestMapper(Mapper[TestSchema]):
            pass  # Uses default _has_field which returns False

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.name == "temperature"  # name is still set to first option
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

        class TestMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

            def _read_value(self, data_source: dict[str, Any], name: str):
                return data_source[name]

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

        class TestMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

            def _read_value(self, data_source: dict[str, Any], name: str):
                return data_source[name]

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

        class TestMapper(Mapper[TestSchema]):
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

        class TestMapper(Mapper[TestSchema]):
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

        class TestMapper(Mapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(data)
        mapped_field = mapper.mapped_fields[mapper.schema.temp]

        assert mapped_field.schema_path == "TestSchema.temp"


class TestFromDefaults:
    """Test from_defaults() class method."""

    def test_from_defaults_creates_mapper(self):
        """from_defaults creates mapper without data_source."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(Mapper[TestSchema]):
            pass

        mapper = TestMapper.from_defaults()

        assert isinstance(mapper, TestMapper)
        assert isinstance(mapper.schema, TestSchema)

    def test_from_defaults_with_defaults_dict(self):
        """from_defaults uses provided default values."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(Mapper[TestSchema]):
            pass

        defaults: dict[MappingBase, Any] = {
            TestMapper.schema.temp: 20.0,
            TestMapper.schema.pressure: 101.3,
        }

        mapper = TestMapper.from_defaults(defaults)

        # Fields should be resolved with DEFAULT source
        temp_field = mapper.mapped_fields[mapper.schema.temp]
        assert temp_field.value == 20.0
        assert temp_field.source == MappedFieldSource.DEFAULT

        pressure_field = mapper.mapped_fields[mapper.schema.pressure]
        assert pressure_field.value == 101.3
        assert pressure_field.source == MappedFieldSource.DEFAULT

    def test_from_defaults_partial_defaults(self):
        """from_defaults with partial defaults marks others as MISSING."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(Mapper[TestSchema]):
            pass

        defaults: dict[MappingBase, Any] = {
            TestMapper.schema.temp: 20.0,
        }

        mapper = TestMapper.from_defaults(defaults)

        # temp should have default value
        temp_field = mapper.mapped_fields[mapper.schema.temp]
        assert temp_field.value == 20.0
        assert temp_field.source == MappedFieldSource.DEFAULT

        # pressure should be MISSING
        pressure_field = mapper.mapped_fields[mapper.schema.pressure]
        assert pressure_field.source == MappedFieldSource.MISSING

    def test_from_defaults_get_name_returns_default(self):
        """get_name returns None for MISSING/DEFAULT fields from from_defaults."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temperature")

        class TestMapper(Mapper[TestSchema]):
            pass

        mapper = TestMapper.from_defaults()

        # get_name should return None since field is not from DATA_SOURCE
        assert mapper.get_name(mapper.schema.temp) is None

    def test_from_defaults_schema_names_accessible(self):
        """Schema default names are accessible via .names[0]."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping(("temperature", "temp_c"))
            pressure: Mapping = Mapping("pressure")

        class TestMapper(Mapper[TestSchema]):
            pass

        mapper = TestMapper.from_defaults()

        # Can access default names from schema
        assert mapper.schema.temp.names[0] == "temperature"
        assert mapper.schema.pressure.names[0] == "pressure"

    def test_from_defaults_simple_schema_use_case(self):
        """from_defaults is useful for schemas without conditional logic."""

        @dataclass
        class SimpleCoordinateSchema(Schema):
            """Simple schema for coordinate names - no conditional resolution."""

            x_coord: Mapping = Mapping("x")
            y_coord: Mapping = Mapping("y")
            z_coord: Mapping = Mapping("z")

        class CoordMapper(Mapper[SimpleCoordinateSchema]):
            pass

        # Create mapper without data_source to access default names
        mapper = CoordMapper.from_defaults()

        # Use default names to create new coordinates
        coord_names = {
            "x": mapper.schema.x_coord.names[0],
            "y": mapper.schema.y_coord.names[0],
            "z": mapper.schema.z_coord.names[0],
        }

        assert coord_names == {"x": "x", "y": "y", "z": "z"}


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

            def resolve(self, context: Mapper) -> Mapping:
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

        class TestMapper(Mapper[TestSchema]):
            def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
                return name in data_source

            def _read_value(self, data_source: dict[str, Any], name: str):
                return data_source[name]

        mapper = TestMapper.from_data_source(data)

        # Version should be resolved first
        assert mapper.mapped_fields[mapper.schema.version].value == 2

        # Data should resolve to v2 based on version
        data_field = mapper.mapped_fields[mapper.schema.data]
        assert data_field.name == "data_v2"
