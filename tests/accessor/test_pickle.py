"""Mapper pickle preserves resolved access without probing data again."""

from __future__ import annotations

import pickle
from dataclasses import dataclass

import pytest
import xarray as xr

from tollan.accessor import Mapping, NameMapping, Schema, SubpathMapping
from tollan.accessor.schema import MISSING, FieldLocation, MappedField
from tollan.accessor.xarray import XarrayMapper


class SelectedSignal(Mapping):
    def resolve(self, context):
        return NameMapping.var(
            context.data_source.attrs["signal_name"], parent=context.schema.output
        )


_signal_mapping = SelectedSignal()


@dataclass
class SignalSchema(Schema):
    output: SubpathMapping = SubpathMapping.path(
        ("preferred", "fallback"), resolve_value=True
    )
    signal: Mapping = _signal_mapping
    optional: NameMapping = NameMapping.attr("optional")
    missing: NameMapping = NameMapping.attr("missing")


class SignalMapper(XarrayMapper[SignalSchema]):
    pass


def test_pickle_keeps_field_bindings_defaults_and_shared_nodes(monkeypatch):
    tree = xr.DataTree.from_dict(
        {"fallback": xr.Dataset({"actual": ("sample", [2.0, 4.0])})}
    )
    tree.attrs["signal_name"] = "actual"
    mapper = SignalMapper.from_data_source(tree, {SignalMapper.schema.optional: 0})
    snapshot = pickle.dumps((tree, mapper))

    def unexpected_resolution(*args, **kwargs):
        pytest.fail("Loading a mapper must not probe the source again")

    monkeypatch.setattr(SelectedSignal, "resolve", unexpected_resolution)
    restored_tree, restored = pickle.loads(snapshot)  # noqa: S301 -- test-owned objects
    schema = restored.schema
    assert restored.get_name(schema.signal) == "actual"
    assert restored.mapped_fields[schema.signal].mapping is schema.signal
    assert (
        restored.get_arr(restored_tree, schema.signal).data
        is restored_tree["fallback/actual"].data
    )
    assert restored.mapped_fields[schema.output].value is restored_tree["fallback"]
    assert restored.get_value_or_default(restored_tree, schema.optional) == 0
    assert restored.mapped_fields[schema.missing].value is MISSING
    with pytest.raises(KeyError):
        restored.get_value_or_default(restored_tree, schema.missing)
    with pytest.raises(TypeError):
        restored.mapped_fields[schema.signal] = restored.mapped_fields[schema.signal]


def test_pickle_preserves_constructor_records_outside_the_schema():
    extra = NameMapping.attr("extra")
    mapper = SignalMapper(
        {
            extra: MappedField(
                mapping=extra,
                mapping_resolved=extra,
                name="extra",
                location=FieldLocation.attr,
            )
        }
    )
    restored = pickle.loads(pickle.dumps(mapper))  # noqa: S301 -- test-owned mapper
    assert restored.get_value(xr.Dataset(attrs={"extra": 3}), extra) == 3
