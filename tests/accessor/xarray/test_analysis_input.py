"""Optional input lookup paired with analysis scope preparation."""

from dataclasses import dataclass

import dask.array as da
import pytest
import xarray as xr

from tollan.accessor import SubpathMapping
from tollan.accessor.xarray import (
    AnalysisInputMapper,
    AnalysisInputSchema,
    AnalysisInputView,
    prepare_analysis_input_view,
)


@pytest.mark.parametrize("kind", ["dataset", "named_array", "unnamed_array"])
def test_direct_input_and_prepared_scope_share_arrays(kind):
    values = da.arange(12, chunks=4)
    source = xr.DataArray(values, dims="time", name="signal", attrs={"units": "K"})
    if kind == "dataset":
        source = source.to_dataset()
    elif kind == "unnamed_array":
        source = source.rename(None)
    expected = source.rename("data") if kind == "unnamed_array" else source
    view = prepare_analysis_input_view(source)
    mapper = AnalysisInputMapper.from_data_source(view._data_source)
    node = mapper.get_input_node(view._data_source)
    assert node is view._data_source["_input"]
    assert view.data_source is node
    variable = "data" if kind == "unnamed_array" else "signal"
    assert node[variable].data is values
    xr.testing.assert_identical(view.unwrap(), expected)
    reopened_view = AnalysisInputView(view._data_source)
    assert reopened_view._data_source is view._data_source
    assert reopened_view.data_source[variable].data is values
    assert set(view._data_source.children) == {"_input"}


@dataclass
class SamplesSchema(AnalysisInputSchema):
    input_subpath: SubpathMapping = SubpathMapping.path(("samples", "_input"))


class SamplesMapper(AnalysisInputMapper[SamplesSchema]):
    pass


class SamplesView(AnalysisInputView[SamplesMapper]):
    pass


@pytest.mark.parametrize("path", ["samples", "_input"])
def test_existing_scope_selects_declared_input_without_restructuring(path):
    source = xr.Dataset({"signal": ("time", da.arange(12, chunks=4))})
    tree = xr.DataTree.from_dict(
        {
            f"measurement/{path}": source,
            f"measurement/{path}/calibration": xr.Dataset({"gain": 2.0}),
        }
    )
    before = tree.copy(deep=False)
    view = prepare_analysis_input_view(
        tree, view_cls=SamplesView, parent_namespace="measurement"
    )
    assert view._data_source is tree["measurement"]
    assert isinstance(view.mapper, SamplesMapper)
    assert view.data_source is tree[f"measurement/{path}"]
    assert view.data_source["calibration"] is tree[f"measurement/{path}/calibration"]
    assert view.unwrap() is tree["measurement"]
    xr.testing.assert_identical(view.data_source.to_dataset(), source)
    xr.testing.assert_identical(tree, before)


@pytest.mark.parametrize("construct", [AnalysisInputView, prepare_analysis_input_view])
def test_invalid_tree_is_not_wrapped_or_restructured(construct):
    tree = xr.DataTree(dataset=xr.Dataset({"signal": ("time", [1, 2])}))
    before = tree.copy(deep=False)
    with pytest.raises(ValueError, match="not an analysis scope"):
        construct(tree)
    xr.testing.assert_identical(tree, before)


@pytest.mark.parametrize("construct", [AnalysisInputView, prepare_analysis_input_view])
def test_missing_input_is_not_created(construct):
    tree = xr.DataTree()
    with pytest.raises(KeyError):
        construct(tree)
    assert not tree.children


@pytest.mark.parametrize("kind", ["array", "dataset"])
def test_direct_view_requires_scope_without_converting_payload(kind):
    source = xr.DataArray(da.arange(12, chunks=4), dims="time", name="signal")
    if kind == "dataset":
        source = source.to_dataset()
    before = source.copy(deep=False)
    with pytest.raises(TypeError, match="requires a DataTree scope"):
        AnalysisInputView(source)
    xr.testing.assert_identical(source, before)
