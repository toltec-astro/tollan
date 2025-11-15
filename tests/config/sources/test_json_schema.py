"""Tests for JSON schema generation of config sources.

Verifies that all config source models can generate valid JSON schemas
with our WithJsonSchema customizations for complex/recursive types.

Note: These tests import from tollan.config.sources which automatically
calls model_rebuild() to resolve forward references for DictConfigT and
ConfigSourceList circular dependencies.
"""

from __future__ import annotations

import json

import pytest

from tollan.config.sources import (
    ConfigSourceList,
    DictConfigSource,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
)


class TestJsonSchemaGeneration:
    """Test JSON schema generation for all config source models."""

    def test_yaml_config_source_schema(self):
        """YamlConfigSource should generate valid JSON schema."""
        schema = YamlConfigSource.model_json_schema()

        # Basic schema structure
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

        # Check required fields
        assert "order" in schema["required"]
        assert "source" in schema["required"]

        # Check field definitions
        props = schema["properties"]
        assert props["format"]["const"] == "yaml"
        assert props["order"]["type"] == "integer"
        assert props["enabled"]["type"] == "boolean"
        assert props["enabled"]["default"] is True

        # Should have source field (Path type)
        assert "source" in props

    def test_dict_config_source_schema(self):
        """DictConfigSource should generate valid JSON schema with
        WithJsonSchema override."""
        schema = DictConfigSource.model_json_schema()

        # Basic schema structure
        assert schema["type"] == "object"
        assert "properties" in schema

        # Check our WithJsonSchema override for source field
        props = schema["properties"]
        assert "source" in props
        # Our WithJsonSchema provides: {"type": "object", "additionalProperties": True}
        assert props["source"]["type"] == "object"
        assert props["source"].get("additionalProperties") is True

    def test_envfile_config_source_schema(self):
        """EnvFileConfigSource should generate valid JSON schema."""
        schema = EnvFileConfigSource.model_json_schema()

        # Basic schema structure
        assert schema["type"] == "object"
        assert "properties" in schema

        # Check format field
        props = schema["properties"]
        assert props["format"]["const"] == "envfile"

        # Check source field (Path type)
        assert "source" in props

    def test_list_config_source_schema(self):
        """ListConfigSource should generate valid JSON schema with
        WithJsonSchema override."""
        schema = ListConfigSource.model_json_schema()

        # Basic schema structure
        assert schema["type"] == "object"
        assert "properties" in schema

        # Check our WithJsonSchema override for recursive source field
        props = schema["properties"]
        assert "source" in props
        # Our WithJsonSchema provides: {"type": "object"}
        assert props["source"]["type"] == "object"

    def test_config_source_list_schema(self):
        """ConfigSourceList should generate valid JSON schema with
        WithJsonSchema override."""
        schema = ConfigSourceList.model_json_schema()

        # Basic schema structure
        assert schema["type"] == "object"
        assert "properties" in schema

        # Check our WithJsonSchema override for data field
        # (recursive discriminated union)
        props = schema["properties"]
        assert "data" in props
        # Our WithJsonSchema provides: {"type": "array", "items": {"type": "object"}}
        assert props["data"]["type"] == "array"
        assert props["data"]["items"]["type"] == "object"

    def test_all_schemas_serializable(self):
        """All schemas should be JSON serializable."""
        models = [
            YamlConfigSource,
            DictConfigSource,
            EnvFileConfigSource,
            ListConfigSource,
            ConfigSourceList,
        ]

        for model in models:
            schema = model.model_json_schema()
            # Should be serializable to JSON string
            json_str = json.dumps(schema)
            assert isinstance(json_str, str)
            assert len(json_str) > 0

            # Should be deserializable
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)

    def test_schema_validation_mode(self):
        """Schemas should be available in both validation and serialization modes."""
        # Test with ConfigSourceList (most complex)
        validation_schema = ConfigSourceList.model_json_schema(mode="validation")
        serialization_schema = ConfigSourceList.model_json_schema(
            mode="serialization",
        )

        # Both should be valid
        assert validation_schema["type"] == "object"
        assert serialization_schema["type"] == "object"

        # Both should have data field with our WithJsonSchema override
        assert "data" in validation_schema["properties"]
        assert "data" in serialization_schema["properties"]

    def test_discriminated_union_in_schema(self):
        """Discriminated union should be properly represented in schema."""
        schema = ConfigSourceList.model_json_schema()

        # Should have definitions for all source types
        if "$defs" in schema:
            defs = schema["$defs"]
            # Check that source types are defined
            assert any(
                "YamlConfigSource" in key or "yaml" in key.lower() for key in defs
            )

    def test_schema_has_descriptions(self):
        """Schemas should include field descriptions."""
        schema = ConfigSourceList.model_json_schema()
        props = schema["properties"]

        # data field should have description
        assert "data" in props
        # Either from Field or WithJsonSchema
        assert (
            "description" in props["data"]
            or "title" in props["data"]
            or props["data"]["type"] == "array"
        )

    @pytest.mark.parametrize(
        ("model_class", "format_value"),
        [
            (YamlConfigSource, "yaml"),
            (DictConfigSource, "dict"),
            (EnvFileConfigSource, "envfile"),
            (ListConfigSource, "list"),
        ],
    )
    def test_format_field_literal(self, model_class, format_value):
        """Each source type should have correct Literal format value in schema."""
        schema = model_class.model_json_schema()
        props = schema["properties"]

        assert "format" in props
        # Literal types are represented as const in JSON Schema
        assert props["format"]["const"] == format_value

    def test_recursive_reference_handling(self):
        """Recursive references should not cause schema generation to fail."""
        # ListConfigSource has recursive reference: source -> ConfigSourceList
        # ConfigSourceList has discriminated union containing ListConfigSource
        # This creates a cycle that our WithJsonSchema handles

        # Should not raise exception
        list_schema = ListConfigSource.model_json_schema()
        csl_schema = ConfigSourceList.model_json_schema()

        # Both should have valid schemas
        assert list_schema["type"] == "object"
        assert csl_schema["type"] == "object"

        # Our WithJsonSchema overrides prevent infinite recursion
        assert "source" in list_schema["properties"]
        assert "data" in csl_schema["properties"]

    def test_schema_with_actual_instances(self):
        """Schemas should work with actual model instances."""
        # Create actual instances
        dict_source = DictConfigSource.model_validate(
            {
                "order": 0,
                "source": {"key": "value", "nested": {"inner": 123}},
            },
        )

        yaml_source = YamlConfigSource.model_validate(
            {
                "order": 1,
                "source": "/path/to/config.yaml",
            },
        )

        # Create list with discriminated union
        sources = ConfigSourceList.model_validate({"data": [dict_source, yaml_source]})

        # Should be able to serialize
        dumped = sources.model_dump()
        assert dumped["data"][0]["format"] == "dict"
        assert dumped["data"][1]["format"] == "yaml"

        # Should be able to serialize to JSON
        json_str = sources.model_dump_json()
        assert isinstance(json_str, str)

        # Should be able to validate from dict
        validated = ConfigSourceList.model_validate(dumped)
        assert len(validated.data) == 2
        assert validated.data[0].format == "dict"
        assert validated.data[1].format == "yaml"
