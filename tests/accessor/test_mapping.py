"""Test Mapping convenience syntax for creating FieldMapping instances."""

from __future__ import annotations

import pytest

from tollan.accessor.schema import FieldMapping, Mapping


def test_mapping_from_string():
    """Test creating Mapping from a string field name."""
    m = Mapping("field_name")
    assert isinstance(m, FieldMapping)
    assert m.names == ("field_name",)
    assert m.required is True
    assert m.resolve_value is False


def test_mapping_from_string_with_kwargs():
    """Test creating Mapping from string with keyword arguments."""
    m = Mapping("field_name", required=False, resolve_value=True)
    assert m.names == ("field_name",)
    assert m.required is False
    assert m.resolve_value is True


def test_mapping_from_tuple():
    """Test creating Mapping from tuple of alternative field names."""
    m = Mapping(("field1", "field2", "field3"))
    assert m.names == ("field1", "field2", "field3")
    assert m.required is True


def test_mapping_from_tuple_with_kwargs():
    """Test creating Mapping from tuple with keyword arguments."""
    m = Mapping(("alt1", "alt2"), required=False)
    assert m.names == ("alt1", "alt2")
    assert m.required is False


def test_mapping_from_list():
    """Test creating Mapping from list (converted to tuple internally)."""
    m = Mapping(["field1", "field2"])
    assert m.names == ("field1", "field2")


def test_mapping_rejects_invalid_names():
    """Test that invalid names types are caught by validation."""
    with pytest.raises(ValueError, match="names must be str or tuple"):
        Mapping(123)


def test_mapping_equality():
    """Test that different syntaxes produce equivalent Mapping instances."""
    m1 = Mapping("test", required=False, resolve_value=True)
    m2 = Mapping("test", required=False, resolve_value=True)

    assert m1.names == m2.names
    assert m1.required == m2.required
    assert m1.resolve_value == m2.resolve_value


def test_mapping_resolve():
    """Test that resolve() returns the Mapping itself (which is a FieldMapping)."""
    m = Mapping("field", required=False)
    resolved = m.resolve(context=None)

    assert resolved is m
    assert isinstance(resolved, FieldMapping)
    assert resolved.names == ("field",)
    assert resolved.required is False


def test_mapping_in_schema():
    """Test using Mapping in a dataclass schema."""
    from pydantic.dataclasses import dataclass

    from tollan.accessor.schema import Schema

    @dataclass
    class TestSchema(Schema):
        simple: Mapping = Mapping("simple_field")
        with_kwargs: Mapping = Mapping("optional_field", required=False)
        alternatives: Mapping = Mapping(("alt1", "alt2"))
        with_resolve: Mapping = Mapping("eager_field", resolve_value=True)

    schema = TestSchema()

    assert schema.simple.names == ("simple_field",)
    assert schema.with_kwargs.required is False
    assert schema.alternatives.names == ("alt1", "alt2")
    assert schema.with_resolve.resolve_value is True
