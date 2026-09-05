"""Test Mapping convenience syntax for field mapping."""

from __future__ import annotations

import pytest

from tollan.accessor.schema import Mapping, MappingContext, NameMapping, Schema


def test_mapping_from_string():
    """Test creating Mapping from a string field name."""
    m = NameMapping("field_name")
    assert isinstance(m, Mapping)
    assert m.names == ("field_name",)
    assert m.resolve_value is False


def test_mapping_from_string_with_kwargs():
    """Test creating Mapping from string with keyword arguments."""
    m = NameMapping("field_name", resolve_value=True)
    assert m.names == ("field_name",)
    assert m.resolve_value is True


def test_mapping_from_tuple():
    """Test creating Mapping from tuple of alternative field names."""
    m = NameMapping(("field1", "field2", "field3"))
    assert m.names == ("field1", "field2", "field3")


def test_mapping_from_tuple_with_kwargs():
    """Test creating Mapping from tuple with keyword arguments."""
    m = NameMapping(("alt1", "alt2"), resolve_value=True)
    assert m.names == ("alt1", "alt2")
    assert m.resolve_value is True


def test_mapping_from_list():
    """Test creating Mapping from list (converted to tuple internally)."""
    m = NameMapping(["field1", "field2"])
    assert m.names == ("field1", "field2")


def test_mapping_rejects_invalid_names():
    """Test that invalid names types are caught by validation."""
    with pytest.raises(ValueError, match="string, tuple of strings"):
        NameMapping(123)  # ty: ignore[invalid-argument-type]


def test_mapping_equality():
    """Test that different syntaxes produce equivalent Mapping instances."""
    m1 = NameMapping("test", resolve_value=True)
    m2 = NameMapping("test", resolve_value=True)

    assert m1.names == m2.names
    assert m1.resolve_value == m2.resolve_value


def test_mapping_resolve():
    """Test that resolve() returns the Mapping itself (which is a Mapping)."""
    m = NameMapping("field")
    resolved = m.resolve(MappingContext(None, Schema(), {}))

    assert resolved is m
    assert isinstance(resolved, Mapping)
    assert resolved.names == ("field",)


def test_mapping_in_schema():
    """Test using Mapping in a dataclass schema."""
    from dataclasses import dataclass

    from tollan.accessor.schema import Schema

    @dataclass
    class TestSchema(Schema):
        simple: Mapping = NameMapping("simple_field")
        alternatives: Mapping = NameMapping(("alt1", "alt2"))
        with_resolve: Mapping = NameMapping("eager_field", resolve_value=True)

    schema = TestSchema()

    assert isinstance(schema.simple, NameMapping)
    assert isinstance(schema.alternatives, NameMapping)
    assert isinstance(schema.with_resolve, NameMapping)
    assert schema.simple.names == ("simple_field",)
    assert schema.alternatives.names == ("alt1", "alt2")
    assert schema.with_resolve.resolve_value is True
