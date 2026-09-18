"""Test Mapping convenience syntax for field mapping."""

from __future__ import annotations

import pytest

from tollan.accessor.schema import (
    FieldLocation,
    Mapping,
    MappingContext,
    NameMapping,
    Schema,
)


@pytest.mark.parametrize("location", list(FieldLocation))
def test_location_factories(location):
    factory = getattr(NameMapping, location.value)
    mapping = factory(("first", "second"), resolve_value=True)
    assert mapping.candidates == (("first", location), ("second", location))
    assert mapping.names == ("first", "second")
    assert mapping.resolve_value is True
    assert factory("first") == NameMapping([("first", location)])
    assert hash(factory("first")) == hash(NameMapping([("first", location)]))


def test_same_name_in_different_locations_is_distinct():
    mapping = NameMapping([("count", FieldLocation.dim), ("count", FieldLocation.attr)])
    assert mapping.names == ("count", "count")
    assert NameMapping.dim("count") != NameMapping.attr("count")
    assert len({NameMapping.dim("count"), NameMapping.attr("count")}) == 2


@pytest.mark.parametrize(
    "candidates",
    [
        [("count", FieldLocation.dim), ("count", FieldLocation.dim)],
        [("count", "unsupported")],
        [("count", FieldLocation.dim, "extra")],
        ("count", FieldLocation.dim),
    ],
)
def test_invalid_location_candidates(candidates):
    with pytest.raises(ValueError):
        NameMapping(candidates)


def test_normalized_candidates_have_named_fields():
    mapping = NameMapping([("sample", FieldLocation.dim), ("count", None)])
    candidate = mapping.candidates[0]
    assert candidate.name == "sample"
    assert candidate.location is FieldLocation.dim
    assert mapping.candidates[1].name == "count"
    assert mapping.candidates[1].location is None
    assert mapping.candidates == (("sample", FieldLocation.dim), ("count", None))


@pytest.mark.parametrize("candidates", [[{"name": "sample", "location": "dim"}]])
def test_candidate_dict_is_not_an_input_form(candidates):
    with pytest.raises(ValueError):
        NameMapping(candidates)


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
    with pytest.raises(ValueError, match="name or a sequence"):
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
