"""Parent mappings select a coherent subtree without loading array values."""

from dataclasses import dataclass, replace

import dask.array as da
import pytest
import xarray as xr
from dask import delayed

from tollan.accessor import Mapping, NameMapping, Schema, SubpathMapping
from tollan.accessor.xarray import XarrayMapper


@dataclass
class ResultsSchema(Schema):
    output: SubpathMapping = SubpathMapping.path(("preferred", "fallback"))
    signal: Mapping = output / NameMapping.var(("signal", "voltage"))
    frequency: Mapping = NameMapping.var("frequency", parent=output)
    units: Mapping = output / NameMapping.attr("units")
    count: Mapping = output / NameMapping.dim("sample")
    calibration: Mapping = output / NameMapping.path("calibration")
    label: Mapping = output / NameMapping.var("label")


class ResultsMapper(XarrayMapper[ResultsSchema]):
    pass


@pytest.fixture
def tree():
    @delayed
    def unread():
        pytest.fail("Mapping must not load signal data")

    data = xr.Dataset(
        {
            "voltage": ("sample", da.from_delayed(unread(), shape=(2,), dtype=float)),
            "label": "measurement",
        },
        coords={"frequency": ("sample", [1.0, 2.0])},
        attrs={"units": "V"},
    )
    return xr.DataTree.from_dict(
        {"fallback": data, "fallback/calibration": xr.Dataset()}
    )


def test_parent_lookup_all_locations_is_lazy(tree):
    mapper = ResultsMapper.from_data_source(tree)
    schema = mapper.schema
    assert mapper.get_name(schema.signal) == "voltage"
    assert mapper.mapped_fields[schema.signal].parent_path == "fallback"
    assert mapper.get_arr(tree, schema.signal).data is tree["fallback/voltage"].data
    assert mapper.get_arr(tree, schema.frequency).name == "frequency"
    assert mapper.has_attr(tree, schema.units)
    assert mapper.get_value(tree, schema.units) == "V"
    assert mapper.get_scalar(tree, schema.units) == "V"
    assert mapper.get_str(tree, schema.units) == "V"
    assert mapper.get_str(tree, schema.label) == "measurement"
    assert mapper.get_scalar(tree, schema.label) == "measurement"
    assert mapper.has_dim(tree, schema.count)
    assert mapper.get_dim(tree, schema.count) == 2
    assert mapper.get_scalar(tree, schema.count) == 2
    assert mapper.has_node(tree, schema.calibration)
    assert mapper.get_node(tree, schema.calibration) is tree["fallback/calibration"]
    detached = tree.copy(deep=False)
    assert (
        mapper.get_node(detached, schema.calibration)
        is detached["fallback/calibration"]
    )


def test_parent_is_selected_before_child_candidates(tree):
    tree["preferred"] = xr.DataTree()
    mapper = ResultsMapper.from_data_source(tree)
    assert not mapper.has_arr(tree, mapper.schema.signal)
    with pytest.raises(KeyError):
        mapper.get_arr(tree, mapper.schema.signal)
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "preferred"


def test_reads_do_not_reresolve_parent(tree):
    mapper = ResultsMapper.from_data_source(tree)
    other = xr.DataTree.from_dict({"preferred": tree["fallback"].to_dataset()})
    assert not mapper.has_arr(other, mapper.schema.signal)
    assert not mapper.has_attr(other, mapper.schema.units)
    assert not mapper.has_dim(other, mapper.schema.count)
    assert not mapper.has_node(other, mapper.schema.calibration)
    with pytest.raises(KeyError):
        mapper.get_dim(other, mapper.schema.count)
    assert ResultsMapper.from_data_source(other).has_arr(other, mapper.schema.signal)


def test_schema_override_redirects_inherited_parent(tree, monkeypatch):
    @dataclass
    class CustomSchema(ResultsSchema):
        output: SubpathMapping = SubpathMapping.path("custom")

    @dataclass
    class InheritedSchema(CustomSchema):
        pass

    class CustomMapper(XarrayMapper[InheritedSchema]):
        pass

    source = xr.DataTree.from_dict({"custom": tree["fallback"].to_dataset()})
    mapper = CustomMapper.from_data_source(source)
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "custom"
    assert mapper.get_arr(source, mapper.schema.signal).name == "voltage"
    monkeypatch.setattr(
        CustomMapper,
        "schema",
        replace(CustomMapper.schema, output=SubpathMapping.path("instance")),
    )
    mapper = CustomMapper.from_defaults()
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "instance"


def test_shared_declaration_keeps_schema_specific_attribute_names():
    parent = SubpathMapping.path("data")
    child = parent / NameMapping.var("signal")

    @dataclass
    class FirstSchema(Schema):
        first: SubpathMapping = parent
        signal: Mapping = child

    @dataclass
    class SecondSchema(Schema):
        second: SubpathMapping = parent
        signal: Mapping = child

    class FirstMapper(XarrayMapper[FirstSchema]):
        pass

    class SecondMapper(XarrayMapper[SecondSchema]):
        pass

    first = replace(FirstSchema(), first=SubpathMapping.path("first"))
    second = replace(SecondSchema(), second=SubpathMapping.path("second"))
    FirstMapper.schema = first
    SecondMapper.schema = second
    assert FirstMapper.from_defaults().mapped_fields[child].parent_path == "first"
    assert SecondMapper.from_defaults().mapped_fields[child].parent_path == "second"
    assert FirstSchema.signal is SecondSchema.signal is child
    assert parent.names == ("data",)


@pytest.mark.parametrize("selection", ["first", "second"])
@pytest.mark.parametrize("instance_override", [False, True])
def test_custom_mapping_selects_parent_at_resolution(
    selection, instance_override, monkeypatch
):
    class SelectedSignal(Mapping):
        def resolve(self, context):
            parent = getattr(ChoiceSchema, context.data_source.attrs["selection"])
            return parent / NameMapping.var("signal")

    selected_signal = SelectedSignal()

    @dataclass
    class ChoiceSchema(Schema):
        first: SubpathMapping = SubpathMapping.path("first")
        second: SubpathMapping = SubpathMapping.path("second")
        signal: Mapping = selected_signal

    @dataclass
    class CustomSchema(ChoiceSchema):
        first: SubpathMapping = SubpathMapping.path("custom_first")
        second: SubpathMapping = SubpathMapping.path("custom_second")

    class ChoiceMapper(XarrayMapper[CustomSchema]):
        pass

    if instance_override:
        monkeypatch.setattr(
            ChoiceMapper,
            "schema",
            replace(
                ChoiceMapper.schema,
                first=SubpathMapping.path("instance_first"),
                second=SubpathMapping.path("instance_second"),
            ),
        )
    prefix = "instance" if instance_override else "custom"
    source = xr.DataTree.from_dict(
        {
            "/": xr.Dataset(attrs={"selection": selection}),
            f"{prefix}_first": xr.Dataset({"signal": 1}),
            f"{prefix}_second": xr.Dataset({"signal": 2}),
        }
    )
    mapper = ChoiceMapper.from_data_source(source)
    field = mapper.schema.signal
    assert mapper.mapped_fields[field].parent_path == f"{prefix}_{selection}"
    assert mapper.get_scalar(source, field) == (1 if selection == "first" else 2)


def test_shared_parent_follows_override_in_multiple_inheritance():
    shared = SubpathMapping.path("raw")

    @dataclass
    class B(Schema):
        result: Mapping = shared

    @dataclass
    class A(Schema):
        output: Mapping = shared
        signal: Mapping = output / NameMapping.var("signal")

    @dataclass
    class C(A, B):
        output: Mapping = SubpathMapping.path("processed")

    class CombinedMapper(XarrayMapper[C]):
        pass

    source = xr.DataTree.from_dict(
        {
            "raw": xr.Dataset({"signal": 1}),
            "processed": xr.Dataset({"signal": 2}),
        }
    )
    mapper = CombinedMapper.from_data_source(source)
    assert mapper.get_name(mapper.schema.result) == "raw"
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "processed"
    assert mapper.get_scalar(source, mapper.schema.signal) == 2


def test_equal_parent_mappings_retain_distinct_declarations():
    @dataclass
    class BaseSchema(Schema):
        first: SubpathMapping = SubpathMapping.path("data")
        second: SubpathMapping = SubpathMapping.path("data")
        first_signal: Mapping = first / NameMapping.var("first_signal")
        second_signal: Mapping = second / NameMapping.var("second_signal")

    @dataclass
    class CustomSchema(BaseSchema):
        first: SubpathMapping = SubpathMapping.path("first")
        second: SubpathMapping = SubpathMapping.path("second")

    class CustomMapper(XarrayMapper[CustomSchema]):
        pass

    source = xr.DataTree.from_dict(
        {
            "first": xr.Dataset({"first_signal": 1}),
            "second": xr.Dataset({"second_signal": 2}),
        }
    )
    mapper = CustomMapper.from_data_source(source)
    schema = mapper.schema
    assert BaseSchema.first == BaseSchema.second
    assert BaseSchema.first is not BaseSchema.second
    assert schema._get_path_field_name(BaseSchema.first) == "first"
    assert schema._get_path_field_name(BaseSchema.second) == "second"
    assert mapper.get_scalar(source, schema.first_signal) == 1
    assert mapper.get_scalar(source, schema.second_signal) == 2


def test_nested_composition_and_direct_variable_paths(tree):
    @dataclass
    class NestedSchema(Schema):
        namespace: SubpathMapping = SubpathMapping.path("analysis")
        data: Mapping = namespace / SubpathMapping.path(("preferred", "fallback"))
        signal: Mapping = data / NameMapping.var("voltage")
        direct: Mapping = NameMapping.var("analysis/fallback/voltage")

    class NestedMapper(XarrayMapper[NestedSchema]):
        pass

    source = xr.DataTree()
    source["analysis"] = tree
    mapper = NestedMapper.from_data_source(source)
    assert mapper.get_node(source, mapper.schema.data) is source["analysis/fallback"]
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "analysis/fallback"
    assert mapper.get_arr(source, mapper.schema.signal).identical(
        mapper.get_arr(source, mapper.schema.direct)
    )


def test_missing_parent_defaults_and_eager_scalar_capture():
    @dataclass
    class CaptureSchema(Schema):
        parent: Mapping = NameMapping.path("data")
        rate: Mapping = parent / NameMapping.attr("rate", resolve_value=True)

    class CaptureMapper(XarrayMapper[CaptureSchema]):
        pass

    source = xr.DataTree.from_dict({"data": xr.Dataset(attrs={"rate": 100})})
    field = CaptureMapper.schema.rate
    mapper = CaptureMapper.from_data_source(source, {field: 20})
    assert mapper.mapped_fields[field].value == 100
    assert mapper.get_value_or_default(xr.DataTree(), field) == 20
    defaults = CaptureMapper.from_defaults({field: 20})
    assert defaults.mapped_fields[field].value == 20
    assert defaults.get_value(source, field) == 100


def test_invalid_composition():
    with pytest.raises(ValueError, match="path candidates"):
        NameMapping.var("x") / NameMapping.attr("units")
    parent = SubpathMapping.path("data")
    with pytest.raises(ValueError, match="already has a parent"):
        parent / (parent / NameMapping.var("x"))


def test_self_referencing_override_is_rejected():
    @dataclass
    class SelfReferencingSchema(ResultsSchema):
        output: Mapping = NameMapping.path("nested", parent=ResultsSchema.output)

    class SelfReferencingMapper(XarrayMapper[SelfReferencingSchema]):
        pass

    with pytest.raises(ValueError, match="declared before its child"):
        SelfReferencingMapper.from_defaults()


def test_replaced_schema_redirects_parent(tree, monkeypatch):
    monkeypatch.setattr(
        ResultsMapper,
        "schema",
        replace(ResultsMapper.schema, output=SubpathMapping.path("custom")),
    )
    source = xr.DataTree.from_dict({"custom": tree["fallback"].to_dataset()})
    mapper = ResultsMapper.from_data_source(source)
    assert mapper.get_arr(source, mapper.schema.signal).name == "voltage"
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "custom"


def test_direct_paths_distinguish_nodes_coordinates_and_bare_dimensions(tree):
    @dataclass
    class PathsSchema(Schema):
        coordinate: Mapping = NameMapping.var("fallback/frequency")
        bare_dimension: Mapping = NameMapping.var("fallback/sample")
        node_as_variable: Mapping = NameMapping.var("fallback/calibration")

    class PathsMapper(XarrayMapper[PathsSchema]):
        pass

    mapper = PathsMapper.from_data_source(tree)
    assert mapper.get_arr(tree, mapper.schema.coordinate).values.tolist() == [1.0, 2.0]
    for field in (mapper.schema.bare_dimension, mapper.schema.node_as_variable):
        assert not mapper.has_arr(tree, field)
        with pytest.raises(KeyError):
            mapper.get_arr(tree, field)


def test_backend_without_subtrees_rejects_parent():
    from tollan.accessor.pandas import DataFrameMapper

    class FlatMapper(DataFrameMapper[ResultsSchema]):
        pass

    with pytest.raises(ValueError, match="does not support mapping parents"):
        FlatMapper.from_defaults()


def test_shared_parent_is_resolved_once(tree, monkeypatch):
    resolve = NameMapping.resolve
    calls = []

    def record(mapping, context):
        calls.append(mapping)
        return resolve(mapping, context)

    monkeypatch.setattr(NameMapping, "resolve", record)
    mapper = ResultsMapper.from_data_source(tree)
    assert sum(mapping is mapper.schema.output for mapping in calls) == 1
    assert mapper.mapped_fields[mapper.schema.signal].parent_path == "fallback"
    assert mapper.mapped_fields[mapper.schema.units].parent_path == "fallback"


@pytest.mark.parametrize("declare_later", [False, True])
def test_parent_must_be_an_earlier_schema_field(declare_later):
    parent = SubpathMapping.path("data")

    @dataclass
    class UndeclaredSchema(Schema):
        signal: Mapping = parent / NameMapping.var("signal")

    @dataclass
    class ForwardSchema(UndeclaredSchema):
        data: Mapping = parent

    schema_cls = ForwardSchema if declare_later else UndeclaredSchema

    class InvalidMapper(XarrayMapper[Schema]):
        pass

    InvalidMapper.schema = schema_cls()
    with pytest.raises(ValueError, match="declared before its child"):
        InvalidMapper.from_defaults()
