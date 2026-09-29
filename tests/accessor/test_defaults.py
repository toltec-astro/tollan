"""Explicit fallbacks and source-only reads of a fixed mapping plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import xarray as xr

from tollan.accessor import FieldLocation, Mapping, NameMapping, Schema
from tollan.accessor.schema import MISSING, MappedFieldSource
from tollan.accessor.xarray import XarrayMapper

if TYPE_CHECKING:
    from tollan.accessor import MappingContext


def make_mapper(mapping, source, value_default=MISSING):
    @dataclass
    class FieldSchema(Schema):
        field: Mapping = mapping

    class FieldMapper(XarrayMapper[FieldSchema]):
        pass

    return FieldMapper.from_data_source(source, {mapping: value_default})


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_present_falsey_values_win_over_default(value):
    field = NameMapping.attr("value")
    source = xr.Dataset(attrs={"value": value})
    mapper = make_mapper(field, source, "fallback")
    assert mapper.get_value(source, field) is value
    assert mapper.get_value_or_default(source, field) is value
    assert mapper.mapped_fields[field].value is MISSING
    assert mapper.mapped_fields[field].value_default == "fallback"


@pytest.mark.parametrize("value_default", [None, False, 0, "", [], {}])
def test_falsey_defaults_are_not_missing(value_default):
    field = NameMapping.attr("value")
    source = xr.Dataset()
    mapper = make_mapper(field, source, value_default)
    assert mapper.get_value_or_default(source, field) is value_default
    assert mapper.get_value_or_default(None, field) is value_default
    assert mapper.mapped_fields[field].value is MISSING
    with pytest.raises(KeyError):
        mapper.get_value(source, field)


@pytest.mark.parametrize(
    "location", [FieldLocation.attr, FieldLocation.var, FieldLocation.dim]
)
def test_defaults_remain_available_across_sources(location):
    field = NameMapping([("value", location)])
    present = xr.Dataset({"value": ("value", [8, 9])}, attrs={"value": "present"})
    absent = xr.Dataset()
    for reference in (present, absent, None):
        mapper = make_mapper(field, reference, "fallback")
        assert mapper.get_value_or_default(absent, field) == "fallback"
        assert mapper.get_value_or_default(None, field) == "fallback"
        assert mapper.mapped_fields[field].value_default == "fallback"
        assert mapper.mapped_fields[field].value is MISSING
        if location == FieldLocation.var:
            assert mapper.get_value_or_default(present, field).tolist() == [8, 9]
        else:
            expected = "present" if location == FieldLocation.attr else 2
            assert mapper.get_value_or_default(present, field) == expected
        with pytest.raises(KeyError):
            mapper.get_value(absent, field)


def test_unlocated_field_does_not_infer_a_location_when_read(monkeypatch):
    field = NameMapping("value")
    mapper = make_mapper(field, None, "fallback")
    source = xr.Dataset(attrs={"value": "present"})

    def unexpected_probe(*args):
        pytest.fail("An unlocated field must not infer a location during reads")

    monkeypatch.setattr(mapper, "_has_field", unexpected_probe)
    assert mapper.mapped_fields[field].location is None
    assert mapper.get_value_or_default(source, field) == "fallback"
    with pytest.raises(KeyError):
        mapper.get_value(source, field)


def test_fallback_does_not_retry_candidate_names_or_locations():
    field = NameMapping([("value", FieldLocation.var), ("other", FieldLocation.attr)])
    mapper = make_mapper(field, xr.Dataset({"value": xr.DataArray(1)}), "fallback")
    source = xr.Dataset(attrs={"value": "wrong location", "other": "other candidate"})
    assert mapper.get_value_or_default(source, field) == "fallback"
    with pytest.raises(KeyError):
        mapper.get_value(source, field)


def test_missing_and_unknown_fields_do_not_have_implicit_defaults():
    field = NameMapping.attr("value", resolve_value=True)
    source = xr.Dataset()
    mapper = make_mapper(field, source)
    assert mapper.mapped_fields[field].source is MappedFieldSource.missing
    assert mapper.mapped_fields[field].value is MISSING
    assert mapper.mapped_fields[field].value_default is MISSING
    for current in (source, None):
        with pytest.raises(KeyError):
            mapper.get_value_or_default(current, field)
        with pytest.raises(KeyError):
            mapper.get_value_or_default(current, NameMapping.attr("unrelated"))
    source.attrs["value"] = "present"
    assert mapper.get_value(source, field) == "present"
    assert mapper.get_value_or_default(source, field) == "present"
    assert mapper.get_str(source, field) == "present"


@pytest.mark.parametrize("error_type", [KeyError, AttributeError, ValueError, OSError])
def test_existing_field_read_errors_are_not_replaced_by_defaults(
    monkeypatch, error_type
):
    field = NameMapping.var("value")
    source = xr.Dataset({"value": xr.DataArray(1)})
    mapper = make_mapper(field, source, "fallback")
    error = error_type("read failed")

    def fail_read(var):
        raise error

    monkeypatch.setattr(mapper, "_read_var_values", fail_read)
    with pytest.raises(error_type) as caught:
        mapper.get_value_or_default(source, field)
    assert caught.value is error


def test_defaults_and_lazy_resolution_do_not_read_variable_values(monkeypatch):
    field = NameMapping.var("value")
    source = xr.Dataset({"value": xr.DataArray(1)})
    mapper = make_mapper(field, None, "fallback")

    def unexpected_read(*args):
        pytest.fail("Neither lazy resolution nor fallback should read variable values")

    monkeypatch.setattr(type(mapper), "_get_var", unexpected_read)
    mapper = type(mapper).from_data_source(source, {field: "fallback"})
    assert mapper.mapped_fields[field].value is MISSING
    assert mapper.get_value_or_default(xr.Dataset(), field) == "fallback"


def test_shape_and_dimension_getters_do_not_use_defaults():
    source = xr.Dataset()
    field = NameMapping.var("value")
    mapper = make_mapper(field, source, [1, 2, 3])
    with pytest.raises(KeyError):
        mapper.get_shape(source, field)
    field = NameMapping.dim("value")
    mapper = make_mapper(field, source, 3)
    with pytest.raises(KeyError):
        mapper.get_dim(source, field)


@pytest.mark.parametrize("has_version", [True, False])
def test_eager_resolution_uses_source_then_default_without_changing_later(has_version):
    version = NameMapping.attr("version", resolve_value=True)

    @dataclass(frozen=True)
    class VersionedMapping(Mapping):
        def resolve(self, context: MappingContext) -> NameMapping:
            value = context.mapped_fields[version].value
            return NameMapping.var(f"value_v{value}")

    @dataclass
    class VersionedSchema(Schema):
        version_field: Mapping = version
        value: Mapping = VersionedMapping()

    class VersionedMapper(XarrayMapper[VersionedSchema]):
        pass

    source = xr.Dataset(
        {"value_v1": xr.DataArray(11), "value_v2": xr.DataArray(22)},
        attrs={"version": 2} if has_version else {},
    )
    mapper = VersionedMapper.from_data_source(source, {version: 1})
    mapped = mapper.mapped_fields[version]
    assert mapped.value == (2 if has_version else 1)
    assert mapped.value_default == 1
    assert mapped.source is (
        MappedFieldSource.data_source if has_version else MappedFieldSource.default
    )
    assert mapper.get_value(source, mapper.schema.value) == (22 if has_version else 11)

    source.attrs["version"] = 3
    assert mapper.get_value_or_default(source, version) == 3
    del source.attrs["version"]
    assert mapper.get_value_or_default(source, version) == 1
    assert mapper.mapped_fields[version] is mapped
    assert mapped.value == (2 if has_version else 1)
    assert mapper.get_value(source, mapper.schema.value) == (22 if has_version else 11)
