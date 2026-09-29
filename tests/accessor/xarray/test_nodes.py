"""Schema-owned subtree paths, source scope and lazy lookup."""

from dataclasses import dataclass

import dask.array as da
import pytest
import xarray as xr
from dask import delayed

from tollan.accessor import FieldLocation, Mapping, NameMapping, Schema
from tollan.accessor.schema import MISSING
from tollan.accessor.xarray import XarrayMapper


@dataclass
class TreeSchema(Schema):
    result: Mapping = NameMapping.node(("analysis/spectrum", "spectrum"))
    current: Mapping = NameMapping.node(".")
    root: Mapping = NameMapping.node("/")


class TreeMapper(XarrayMapper[TreeSchema]):
    pass


@pytest.fixture
def tree():
    @delayed
    def unread():
        pytest.fail("Subtree lookup must not read arrays")

    signal = da.from_delayed(unread(), shape=(10,), dtype=float)
    return xr.DataTree.from_dict(
        {"scope/analysis/spectrum": xr.Dataset({"signal": ("sample", signal)})}
    )


def test_relative_paths_survive_detaching_without_loading(tree):
    schema = TreeMapper.schema
    for scope in (tree["scope"], tree["scope"].copy(deep=False)):
        mapper = TreeMapper.from_data_source(scope)
        node = mapper.get_node(scope, schema.result)
        assert node is scope["analysis/spectrum"]
        assert mapper.get_value(scope, schema.result) is node
        assert mapper.get_name(schema.result) == "analysis/spectrum"
        assert mapper.mapped_fields[schema.result].value is MISSING
        assert mapper.get_node(scope, schema.current) is scope
        assert mapper.get_node(scope, schema.root) is scope.root
        assert isinstance(node.dataset.signal.data, da.Array)
        assert mapper.mapped_fields[schema.result].location is FieldLocation.node
        with pytest.raises(ValueError):
            mapper.get_scalar(scope, schema.result)


def test_candidates_are_resolved_once_and_reads_use_supplied_source(tree):
    schema = TreeMapper.schema
    scope = tree["scope/analysis"]
    mapper = TreeMapper.from_data_source(scope)
    assert mapper.get_name(schema.result) == "spectrum"
    other = scope.copy(deep=False)
    assert mapper.get_node(other, schema.result) is other["spectrum"]
    assert mapper.get_node(other, schema.result) is not scope["spectrum"]
    other["spectrum"].orphan()
    other["analysis/spectrum"] = xr.DataTree()
    assert not mapper.has_node(other, schema.result)
    with pytest.raises(KeyError):
        mapper.get_node(other, schema.result)
    resolved = TreeMapper.from_data_source(other)
    assert resolved.get_node(other, schema.result) is other["analysis/spectrum"]


def test_variables_cannot_satisfy_node_mapping():
    source = xr.DataTree.from_dict(
        {"analysis": xr.Dataset({"spectrum": ("sample", [1, 2])})}
    )
    mapper = TreeMapper.from_data_source(source)
    assert mapper.schema.result not in mapper
    assert not mapper.has_node(source, mapper.schema.result)
    with pytest.raises(KeyError):
        mapper.get_node(source, mapper.schema.result)
    with pytest.raises(KeyError):
        mapper.get_node(source, NameMapping.var("spectrum"))
    with pytest.raises(ValueError, match="not found as a variable"):
        mapper.get_arr(source, mapper.schema.result)


@pytest.mark.parametrize("source", [xr.Dataset(), xr.DataArray([1])])
def test_flat_sources_have_no_implicit_nodes(source):
    mapper = TreeMapper.from_data_source(source)
    assert mapper.schema.current not in mapper
    assert not mapper.has_node(source, mapper.schema.current)
    with pytest.raises(KeyError):
        mapper.get_node(source, mapper.schema.current)


def test_node_defaults_and_capture_do_not_load_arrays(tree):
    @dataclass
    class CaptureSchema(Schema):
        result: Mapping = NameMapping.node("scope", resolve_value=True)

    class CaptureMapper(XarrayMapper[CaptureSchema]):
        pass

    field = CaptureMapper.schema.result
    mapper = CaptureMapper.from_data_source(tree, {field: "absent"})
    assert mapper.mapped_fields[field].value is tree["scope"]
    assert mapper.get_value_or_default(xr.DataTree(), field) == "absent"
    assert mapper.get_value_or_default(tree, field) is tree["scope"]


def test_node_and_attribute_with_same_name_require_location():
    @dataclass
    class AmbiguousSchema(Schema):
        field: Mapping = NameMapping("analysis")

    class AmbiguousMapper(XarrayMapper[AmbiguousSchema]):
        pass

    tree = xr.DataTree.from_dict({"analysis": xr.Dataset()})
    tree.attrs["analysis"] = "config"
    with pytest.raises(ValueError, match="Ambiguous field.*attr, node"):
        AmbiguousMapper.from_data_source(tree)
