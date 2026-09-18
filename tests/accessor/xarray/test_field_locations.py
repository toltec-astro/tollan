"""Explicit locations and stable mapper plans for xarray payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest
import xarray as xr

from tollan.accessor import FieldLocation, NameMapping, Schema
from tollan.accessor.schema import MISSING, MappedFieldSource
from tollan.accessor.xarray import XarrayMapper

if TYPE_CHECKING:
    from tollan.accessor import Mapping


def make_mapper(mapping, source, defaults=None):
    @dataclass
    class FieldSchema(Schema):
        field: Mapping = mapping

    class FieldMapper(XarrayMapper[FieldSchema]):
        pass

    return FieldMapper.from_data_source(source, defaults)


@pytest.fixture
def source():
    return xr.Dataset(coords={"sample": [10, 20, 30]}, attrs={"sample": 99})


@pytest.mark.parametrize("wrap", [lambda ds: ds, lambda ds: ds["sample"]])
def test_coordinate_and_dimension_are_ambiguous(wrap):
    source = wrap(xr.Dataset(coords={"sample": [10, 20, 30]}))
    with pytest.raises(ValueError, match="Ambiguous field 'sample'.*var, dim"):
        make_mapper(NameMapping(("sample", "fallback")), source)


@pytest.mark.parametrize("location", list(FieldLocation))
def test_explicit_location_with_colliding_names(source, location):
    mapper = make_mapper(NameMapping([("sample", location)]), source)
    field = mapper.schema.field
    assert mapper.mapped_fields[field].location is location
    assert mapper.has_attr(source, field) is (location == FieldLocation.attr)
    assert mapper.has_arr(source, field) is (location == FieldLocation.var)
    assert mapper.has_dim(source, field) is (location == FieldLocation.dim)
    value = mapper.get_value(source, field)
    if location == FieldLocation.var:
        np.testing.assert_array_equal(value, [10, 20, 30])
        with pytest.raises(KeyError, match="Dimension not found"):
            mapper.get_dim(source, field)
    else:
        assert value == (99 if location == FieldLocation.attr else 3)
        assert mapper.get_scalar(source, field) == value
        with pytest.raises(ValueError, match="not found as a variable"):
            mapper.get_arr(source, field)


@pytest.mark.parametrize(
    ("candidates", "expected", "location"),
    [
        (
            [("sample", FieldLocation.dim), ("sample", FieldLocation.attr)],
            3,
            FieldLocation.dim,
        ),
        (
            [("missing", FieldLocation.dim), ("sample", FieldLocation.attr)],
            99,
            FieldLocation.attr,
        ),
        (
            [("sample", FieldLocation.attr), ("sample", FieldLocation.dim)],
            99,
            FieldLocation.attr,
        ),
    ],
)
def test_mixed_candidates_preserve_order(source, candidates, expected, location):
    mapper = make_mapper(NameMapping(candidates), source)
    assert mapper.get_value(source, mapper.schema.field) == expected
    assert mapper.mapped_fields[mapper.schema.field].location is location


def test_ambiguous_candidate_is_not_skipped(source):
    source.attrs["fallback"] = 42
    with pytest.raises(ValueError, match="Ambiguous field 'sample'"):
        make_mapper(NameMapping(("sample", "fallback")), source)


def test_inferred_location_stays_fixed_across_sources():
    mapping = NameMapping("version", resolve_value=True)
    mapper = make_mapper(mapping, xr.Dataset(attrs={"version": 1}))
    mapped = mapper.mapped_fields[mapping]
    assert mapped.location is FieldLocation.attr
    assert mapped.value == 1

    source = xr.Dataset({"version": xr.DataArray(100)}, attrs={"version": 2})
    assert mapper.get_value(source, mapping) == 2
    assert mapper.get_scalar(source, mapping) == 2
    assert mapped.value == 1
    assert not mapper.has_arr(source, mapping)

    del source.attrs["version"]
    assert not mapper.has_attr(source, mapping)
    with pytest.raises(KeyError, match="version"):
        mapper.get_value(source, mapping)
    with pytest.raises(KeyError, match="version"):
        mapper.get_scalar(source, mapping)


def test_variable_mapping_does_not_fall_back_to_attribute():
    mapping = NameMapping.var("value")
    mapper = make_mapper(mapping, xr.Dataset({"value": xr.DataArray(1)}))
    source = xr.Dataset(attrs={"value": 2})
    assert not mapper.has_arr(source, mapping)
    with pytest.raises(KeyError, match="value"):
        mapper.get_value(source, mapping)
    with pytest.raises(KeyError, match="value"):
        mapper.get_arr(source, mapping)
    assert mapper.mapped_fields[mapping].value is MISSING


def test_location_is_independent_of_default_provenance(source):
    mapping = NameMapping.attr("absent")
    mapper = make_mapper(mapping, source, {mapping: 42})
    assert mapper.mapped_fields[mapping].source is MappedFieldSource.DEFAULT
    assert mapper.mapped_fields[mapping].location is FieldLocation.attr
    assert mapper.get_value_or_default(source, mapping) == 42
    with pytest.raises(KeyError, match="absent"):
        mapper.get_value(source, mapping)
    assert not mapper.has_attr(source, mapping)

    missing = make_mapper(mapping, source)
    assert missing.mapped_fields[mapping].source is MappedFieldSource.MISSING
    assert missing.mapped_fields[mapping].location is FieldLocation.attr
    with pytest.raises(KeyError, match="absent"):
        missing.get_value(source, mapping)
