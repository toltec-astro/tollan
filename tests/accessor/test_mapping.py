"""Mapping construction, candidate locations, identity, and schema integration."""

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


def test_mapping_rejects_invalid_names():
    """Test that invalid names types are caught by validation."""
    with pytest.raises(ValueError, match="name or a sequence"):
        NameMapping(123)  # ty: ignore[invalid-argument-type]


def test_mapping_equality():
    """Test that different syntaxes produce equivalent Mapping instances."""
    m1 = NameMapping("test", resolve_value=True)
    m2 = NameMapping("test", resolve_value=True)

    assert m1 == m2
    assert hash(m1) == hash(m2)
    assert m1 != NameMapping("test", resolve_value=False)


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


@pytest.mark.parametrize(
    ("names", "expected", "resolve_value"),
    [
        ("field", ("field",), False),
        ("field", ("field",), True),
        (("field",), ("field",), False),
        (("first", "second"), ("first", "second"), False),
        (("first", "second"), ("first", "second"), True),
        (["first", "second"], ("first", "second"), False),
    ],
)
def test_name_mapping_input_forms(names, expected, resolve_value):
    mapping = NameMapping(names, resolve_value=resolve_value)
    assert isinstance(mapping, Mapping)
    assert mapping.names == expected
    assert mapping.resolve_value is resolve_value
