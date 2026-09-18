"""Shared mapper operations over per-location backend hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import pytest

from tollan.accessor import FieldLocation, Mapper, NameMapping, Schema
from tollan.accessor.schema import MISSING

if TYPE_CHECKING:
    from tollan.accessor import Mapping

type Source = dict[str, dict[str, int]]


@dataclass
class LocatedSchema(Schema):
    attr: Mapping = NameMapping.attr("value")
    var: Mapping = NameMapping.var("value")
    dim: Mapping = NameMapping.dim("value", resolve_value=True)


class LocatedMapper(Mapper[LocatedSchema, Source]):
    _supported_locations: ClassVar = tuple(FieldLocation)

    def _has_attr(self, data_source: Source, name: str) -> bool:
        return name in data_source["attrs"]

    def _has_var(self, data_source: Source, name: str) -> bool:
        return name in data_source["vars"]

    def _has_dim(self, data_source: Source, name: str) -> bool:
        return name in data_source["dims"]

    def _get_attr(self, data_source: Source, name: str) -> int:
        return data_source["attrs"][name]

    def _get_var(self, data_source: Source, name: str) -> int:
        return data_source["vars"][name]

    def _get_dim(self, data_source: Source, name: str) -> int:
        return data_source["dims"][name]


@pytest.fixture
def source():
    return {"attrs": {"value": 11}, "vars": {"value": 22}, "dims": {"value": 3}}


def test_base_dispatches_to_backend_hooks(source):
    mapper = LocatedMapper.from_data_source(source)
    schema = mapper.schema
    assert mapper.has_attr(source, schema.attr)
    assert not mapper.has_attr(source, schema.var)
    assert mapper.has_dim(source, schema.dim)
    assert not mapper.has_dim(source, schema.var)
    assert mapper.get_value(source, schema.attr) == 11
    assert mapper.get_value(source, schema.var) == 22
    assert mapper.get_value(source, schema.dim) == 3
    assert mapper.get_dim(source, schema.dim) == 3
    for field in (schema.attr, schema.var, schema.dim):
        mapper.validate_has_field(field)
    assert mapper.mapped_fields[schema.attr].value is MISSING
    assert mapper.mapped_fields[schema.var].value is MISSING
    assert mapper.mapped_fields[schema.dim].value == 3


def test_dimension_read_uses_current_source_not_capture(source):
    mapper = LocatedMapper.from_data_source(source)
    current = {"attrs": {}, "vars": {}, "dims": {"value": 4}}
    assert mapper.get_dim(current, mapper.schema.dim) == 4
    assert mapper.get_value(current, mapper.schema.dim) == 4
    assert mapper.mapped_fields[mapper.schema.dim].value == 3


def test_missing_dimension_does_not_use_other_locations(source):
    mapper = LocatedMapper.from_data_source(source)
    del source["dims"]["value"]
    assert not mapper.has_dim(source, mapper.schema.dim)
    assert not mapper.has_attr(source, mapper.schema.dim)
    with pytest.raises(KeyError):
        mapper.get_dim(source, mapper.schema.dim)
    with pytest.raises(KeyError):
        mapper.get_dim(source, mapper.schema.var)
    with pytest.raises(KeyError):
        mapper.get_dim(source, NameMapping.dim("unrelated"))


def test_base_defaults_do_not_require_backend_reads():
    mapper = LocatedMapper.from_defaults({LocatedMapper.schema.dim: 42})
    source = {"attrs": {}, "vars": {}, "dims": {}}
    assert mapper.get_value_or_default(source, mapper.schema.dim) == 42
    assert mapper.mapped_fields[mapper.schema.dim].value == 42
    assert mapper.mapped_fields[mapper.schema.dim].value_default == 42
    with pytest.raises(KeyError):
        mapper.get_value(source, mapper.schema.dim)
    with pytest.raises(KeyError):
        mapper.get_dim(source, mapper.schema.dim)
    with pytest.raises(ValueError, match="Missing required field"):
        mapper.validate_has_field(mapper.schema.dim)


def test_unsupported_dimensions_have_no_backend_reads():
    @dataclass
    class VariableSchema(Schema):
        var: Mapping = NameMapping.var("value")

    class VariableMapper(Mapper[VariableSchema, dict[str, int]]):
        def _has_var(self, data_source: dict[str, int], name: str) -> bool:
            return name in data_source

        def _get_var(self, data_source: dict[str, int], name: str) -> int:
            return data_source[name]

    source = {"value": 22}
    mapper = VariableMapper.from_data_source(source)
    assert mapper.get_value(source, mapper.schema.var) == 22
    assert not mapper.has_dim(source, mapper.schema.var)
    assert not mapper.has_attr(source, mapper.schema.var)
    with pytest.raises(KeyError):
        mapper.get_dim(source, mapper.schema.var)
