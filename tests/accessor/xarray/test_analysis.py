"""Shared analysis boundaries, scoped results and lazy array ownership."""

from dataclasses import dataclass
from pathlib import PurePosixPath

import dask.array as da
import numpy as np
import pytest
import xarray as xr

from tollan.accessor import AccessorBase, Mapping, NameMapping, SubpathMapping
from tollan.accessor.xarray import (
    Analysis,
    AnalysisInputMapper,
    AnalysisInputSchema,
    AnalysisMapper,
    AnalysisSchemaMixin,
    AnalysisView,
    XarrayMapper,
    ensure_analysis_scope,
)


@dataclass
class SampleSchema(AnalysisSchemaMixin, AnalysisInputSchema):
    namespace: Mapping = SubpathMapping.path("example.sample")
    analysis: Mapping = NameMapping.attr("example.sample.analysis")
    sample_subpath: Mapping = SubpathMapping.path("sample")
    values: Mapping = NameMapping.var("values")


class SampleMapper(AnalysisMapper[SampleSchema], AnalysisInputMapper[SampleSchema]):
    pass


class SampleInput:
    def __call__(self, data, *, parent_namespace=None, force=False, **kwargs):
        source = data.data_source if isinstance(data, AccessorBase) else data
        scope = ensure_analysis_scope(source, parent_namespace=parent_namespace)
        mapper = self._mapper_cls.from_data_source(scope)
        namespace = PurePosixPath(mapper.get_name(mapper.schema.namespace))
        input_path = PurePosixPath(mapper.get_name(mapper.schema.input_subpath))
        if namespace.is_relative_to(input_path) or input_path.is_relative_to(namespace):
            msg = "Analysis input and namespace must be separate subtrees"
            raise ValueError(msg)
        view = (
            data
            if isinstance(data, AccessorBase)
            else AccessorBase(
                mapper.get_node(scope, mapper.schema.input_subpath).to_dataset(),
                mapper=XarrayMapper.from_defaults(),
            )
        )
        self._call(
            scope,
            mapper=mapper,
            compute=lambda: self._compute_result(view, mapper=mapper, **kwargs),
            can_reuse=lambda saved: "sample" in saved.children,
            force=force,
        )
        return source if isinstance(source, xr.DataTree) else scope


class SampleAnalysis(SampleInput, Analysis[SampleMapper]):
    step: int = 2

    def _get_output_subpaths(self, *, mapper):
        return (mapper.schema.sample_subpath,)

    def _compute_result(self, data, *, mapper, **kwargs):
        return {
            mapper.schema.sample_subpath: data.data_source.isel(
                time=slice(None, None, self.step)
            )
        }


class SampleView(AnalysisView[SampleMapper, SampleAnalysis]):
    @property
    def sample_analysis(self):
        return self._analysis_snapshot

    @property
    def sample(self):
        return self.mapper.get_node(
            self.data_source, self.mapper.schema.sample_subpath
        ).to_dataset()


def test_analysis_snapshot_is_captured_at_view_construction(source):
    tree = SampleAnalysis(step=3)(source)
    mapper = SampleMapper.from_data_source(tree)
    view = SampleView(tree, mapper=mapper)
    assert view.mapper is mapper
    assert view._analysis_cls is SampleAnalysis
    SampleAnalysis(step=4)._dump_to_attr(view.data_source, mapper=mapper)
    # Change attrs before the first public property access: the old snapshot stays.
    assert view.sample_analysis == SampleAnalysis(step=3)
    assert view.sample_analysis is view._analysis_snapshot
    assert SampleView(tree).sample_analysis == SampleAnalysis(step=4)


def test_analysis_class_binding_through_intermediate_view(source):
    class IntermediateView[AnalysisT: Analysis](AnalysisView[SampleMapper, AnalysisT]):
        pass

    class ConcreteView(IntermediateView[SampleAnalysis]):
        pass

    view = ConcreteView(SampleAnalysis(step=3)(source))
    assert view._analysis_cls is SampleAnalysis
    assert view._analysis_snapshot == SampleAnalysis(step=3)


@pytest.mark.parametrize("container", ["array", "dataset", "tree"])
def test_analysis_attribute_protocol_roundtrip(container):
    array = xr.DataArray([1.0, 2.0], dims="sample", name="signal")
    owner = {
        "array": array,
        "dataset": array.to_dataset(),
        "tree": xr.DataTree(dataset=array.to_dataset()),
    }[container]
    owner.attrs["description"] = "preserved"
    assert (
        SampleAnalysis._load_from_attr(
            owner, mapper=SampleMapper.from_data_source(owner)
        )
        is None
    )
    analysis = SampleAnalysis(step=3)
    analysis._dump_to_attr(owner, mapper=SampleMapper.from_data_source(owner))
    restored = SampleAnalysis._load_from_attr(
        owner, mapper=SampleMapper.from_data_source(owner)
    )
    assert type(restored) is SampleAnalysis
    assert restored == analysis
    assert restored is not analysis
    assert owner.attrs == {
        "description": "preserved",
        "example.sample.analysis": '{"step":3}',
    }


@pytest.mark.parametrize("config", [None, "invalid JSON", '{"step":"invalid"}'])
def test_analysis_attribute_protocol_rejects_invalid_present_config(config):
    owner = xr.Dataset(attrs={"example.sample.analysis": config})
    with pytest.raises(ValueError):
        SampleAnalysis._load_from_attr(
            owner, mapper=SampleMapper.from_data_source(owner)
        )
    assert owner.attrs["example.sample.analysis"] == config


def test_analysis_attribute_protocol_reads_only_selected_owner():
    tree = xr.DataTree.from_dict(
        {"namespace": xr.Dataset(), "namespace/child": xr.Dataset()}
    )
    analysis = SampleAnalysis()
    analysis._dump_to_attr(
        tree["namespace"], mapper=SampleMapper.from_data_source(tree["namespace"])
    )
    assert (
        SampleAnalysis._load_from_attr(tree, mapper=SampleMapper.from_data_source(tree))
        is None
    )
    assert (
        SampleAnalysis._load_from_attr(
            tree["namespace/child"],
            mapper=SampleMapper.from_data_source(tree["namespace/child"]),
        )
        is None
    )
    assert (
        SampleAnalysis._load_from_attr(
            tree["namespace"], mapper=SampleMapper.from_data_source(tree["namespace"])
        )
        == analysis
    )


@pytest.fixture
def source():
    return xr.Dataset(
        {"values": ("time", da.arange(12, chunks=4))},
        coords={"time": np.arange(12)},
        attrs={"description": "source"},
    )


def test_promotion_preserves_lazy_input_and_independent_coordinates(source):
    tree = SampleAnalysis()(source)
    assert not tree.dataset.variables
    assert tree["_input"].dataset["values"].data is source["values"].data
    assert tree["_input"].sizes["time"] == 12
    view = SampleView(tree)
    assert isinstance(view.sample["values"].data, da.Array)
    assert view.sample.sizes["time"] == 6
    assert view.sample_analysis == SampleAnalysis(step=2)
    assert source.attrs == {"description": "source"}
    assert source.sizes["time"] == 12


def test_explicit_input_view_and_contextual_mapper(source, monkeypatch):
    input_view = AccessorBase(source, mapper=XarrayMapper.from_data_source(source))
    original_compute = SampleAnalysis._compute_result
    original_dump = SampleAnalysis._dump_to_attr
    resolved = []

    def compute(self, data, *, mapper, **kwargs):
        assert data is input_view
        resolved.append(mapper)
        return original_compute(self, data, mapper=mapper, **kwargs)

    def dump(self, owner, *, mapper):
        assert mapper is resolved[-1]
        original_dump(self, owner, mapper=mapper)

    monkeypatch.setattr(SampleAnalysis, "_compute_result", compute)
    monkeypatch.setattr(SampleAnalysis, "_dump_to_attr", dump)
    analysis = SampleAnalysis()
    assert analysis._mapper_cls is SampleMapper
    assert not hasattr(analysis, "_mapper")
    first = analysis(input_view)
    second = analysis(input_view)
    assert resolved[0] is not resolved[1]
    xr.testing.assert_identical(first, second)
    assert first["_input"].dataset["values"].data is source["values"].data


def test_recompute_replaces_grid_and_dependents_preserving_siblings(source):
    analysis = SampleAnalysis()
    tree = analysis(source)
    tree["example.sample/dependent"] = xr.DataTree(dataset=xr.Dataset({"a": 1}))
    tree["unrelated"] = xr.DataTree(dataset=xr.Dataset({"b": 2}))
    namespace = tree["example.sample"]
    unrelated = tree["unrelated"]
    assert analysis(tree) is tree
    assert tree["example.sample"] is namespace
    assert "dependent" in namespace.children
    updated = SampleAnalysis(step=3)(tree)
    assert SampleView(updated).sample.sizes["time"] == 4
    assert "dependent" not in updated["example.sample"].children
    assert updated is tree
    assert updated["unrelated"] is unrelated
    forced = analysis(tree, force=True)
    assert forced is tree
    assert "dependent" not in forced["example.sample"].children


def test_local_scope_detachment_and_namespace_roundtrip(source, tmp_path):
    tree = xr.DataTree.from_dict({"measurements/one/_input": source})
    result = SampleAnalysis()(tree, parent_namespace="measurements/one")
    assert result is tree
    scope = result["measurements/one"]
    detached = scope["example.sample"].copy(deep=False)
    for selected in (scope, detached, SampleView(detached).data_source):
        view = SampleView(selected)
        assert view._data_source is selected
        assert view.sample_analysis == SampleAnalysis(step=2)
        xr.testing.assert_identical(view.data_source, SampleView(scope).data_source)
    target = tmp_path / "analysis.zarr"
    detached.to_zarr(target)
    with xr.open_datatree(target, engine="zarr") as reopened:
        restored = SampleView(reopened)
        assert restored.sample_analysis == SampleView(detached).sample_analysis
        xr.testing.assert_identical(restored.sample, SampleView(detached).sample)
    assert "example.sample.analysis" not in detached["sample"].attrs
    assert detached.attrs["example.sample.analysis"] == '{"step":2}'


def test_invalid_tree_scopes_raise_without_restructuring(source):
    tree = xr.DataTree(dataset=source)
    tree["other"] = xr.DataTree(dataset=xr.Dataset({"other": ("time", np.ones(12))}))
    expected = tree.copy(deep=False)
    with pytest.raises(ValueError, match="not an analysis scope"):
        SampleAnalysis()(tree)
    xr.testing.assert_identical(tree, expected)
    with pytest.raises(KeyError):
        SampleAnalysis()(xr.DataTree())
    with pytest.raises(TypeError, match="requires a DataTree"):
        SampleAnalysis()(source, parent_namespace="measurement")
    with pytest.raises(TypeError, match="identify a DataTree node"):
        SampleAnalysis()(tree, parent_namespace="values")


def test_module_workflow():
    import doctest

    from tollan.accessor.xarray import analysis

    assert doctest.testmod(analysis, raise_on_error=True).attempted > 0


@pytest.mark.parametrize("path", [".", "/"])
def test_explicit_root_scope(source, path):
    tree = xr.DataTree.from_dict({"_input": source})
    result = SampleAnalysis()(tree, parent_namespace=path)
    assert SampleView(result).sample.sizes["time"] == 6
    assert result is tree


@pytest.mark.parametrize("name", [None, "voltage"])
def test_analysis_promotion_preserves_dataarray_wrapper(name):
    from tollan.accessor.xarray import (
        ensure_analysis_scope,
        ensure_dataset,
        unwrap_data_source,
    )

    source = xr.DataArray(
        da.arange(12, chunks=4), dims="time", attrs={"units": "V"}
    ).rename(name)
    expected = ensure_dataset(source)
    for supplied in (source, expected, ensure_analysis_scope(source)):
        result = SampleAnalysis()(supplied)
        mapper = SampleMapper.from_data_source(result)
        payload = mapper.get_input_node(result)
        xr.testing.assert_identical(payload.to_dataset(), expected)
        restored = unwrap_data_source(payload)
        assert isinstance(restored, xr.DataArray)
        assert restored.name == (name or "data")
        assert restored.attrs == source.attrs
        assert restored.data is source.data
        assert isinstance(SampleView(result).sample[name or "data"].data, da.Array)


@pytest.mark.parametrize("kind", ["dataset", "dataarray"])
@pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")
@pytest.mark.parametrize("engine", ["zarr", "netcdf4"])
def test_scope_roundtrip_preserves_container_type_and_marker(
    source, tmp_path, kind, engine
):
    from tollan.accessor.xarray import ensure_analysis_scope, unwrap_analysis_scope

    supplied = source if kind == "dataset" else source["values"]
    scope = ensure_analysis_scope(supplied)
    assert ensure_analysis_scope(scope) is scope
    restored = unwrap_analysis_scope(scope)
    assert type(restored) is type(supplied)
    xr.testing.assert_identical(restored, supplied)
    arr = restored["values"] if kind == "dataset" else restored
    assert arr.data is source["values"].data
    target = tmp_path / ("scope.zarr" if engine == "zarr" else "scope.nc")
    if engine == "zarr":
        scope.to_zarr(target)
    else:
        scope.to_netcdf(target, engine=engine)
    with xr.open_datatree(target, engine=engine) as reopened:
        xr.testing.assert_identical(unwrap_analysis_scope(reopened), supplied)


def test_scope_selection_and_unmarked_input_are_identity_operations(source):
    from tollan.accessor.xarray import ensure_analysis_scope, unwrap_analysis_scope

    tree = xr.DataTree.from_dict({"blocks/0/_input": source})
    selected = ensure_analysis_scope(tree, parent_namespace="blocks/0")
    assert selected is tree["blocks/0"]
    assert selected.parent is tree["blocks"]
    assert unwrap_analysis_scope(selected) is selected
    assert SampleAnalysis()(selected) is selected
    assert "example.sample" in tree["blocks/0"].children


def test_scope_rejects_inherited_coordinates_and_local_scalars():
    from tollan.accessor.xarray import ensure_analysis_scope

    tree = xr.DataTree.from_dict(
        {"/": xr.Dataset(coords={"time": [0, 1]}), "child": xr.Dataset()}
    )
    with pytest.raises(ValueError, match="/child"):
        ensure_analysis_scope(tree, parent_namespace="child")
    with pytest.raises(ValueError, match="not an analysis scope"):
        ensure_analysis_scope(xr.DataTree(dataset=xr.Dataset({"scalar": 1})))
    with pytest.raises(KeyError):
        ensure_analysis_scope(tree, parent_namespace="missing")


@pytest.mark.parametrize(
    "ancestor",
    [
        xr.Dataset(coords={"time": [0, 1]}),
        xr.Dataset(coords={"label": ("sample", [0, 1])}),
        xr.Dataset(coords={"reference": 1}),
        xr.Dataset({"signal": ("sample", [0, 1])}),
    ],
    ids=["index", "auxiliary-coordinate", "scalar-coordinate", "unindexed-dimension"],
)
def test_scope_rejects_inherited_context_while_view_remains_readable(ancestor):
    from tollan.accessor.xarray import ensure_analysis_scope

    tree = xr.DataTree.from_dict(
        {
            "/": ancestor,
            "intermediate/selected": xr.Dataset(
                attrs={"example.sample.analysis": SampleAnalysis().model_dump_json()}
            ),
        }
    )
    node = tree["intermediate/selected"]
    assert not node.to_dataset(inherit=False).variables
    with pytest.raises(ValueError, match="not an analysis scope"):
        ensure_analysis_scope(node)
    assert SampleView(node).data_source is node


def test_scope_allows_uninherited_scalar_data_in_ancestors(source):
    from tollan.accessor.xarray import ensure_analysis_scope

    tree = xr.DataTree.from_dict(
        {"/": xr.Dataset({"scalar": 1}), "selected/_input": source}
    )
    node = tree["selected"]
    assert ensure_analysis_scope(node) is node
    assert SampleAnalysis()(node) is node
    assert SampleView(node).sample.sizes["time"] == 6


@pytest.mark.parametrize("existing_result", [False, True])
def test_failed_computation_leaves_existing_tree_unchanged(source, existing_result):
    tree = xr.DataTree.from_dict({"_input": source})
    if existing_result:
        SampleAnalysis()(tree)
    before = tree.copy(deep=False)
    with pytest.raises(ValueError):
        SampleAnalysis(step=0)(tree)
    xr.testing.assert_identical(tree, before)


def test_multiple_outputs_have_independent_coordinates(source):
    # Output fields are declared by the concrete schema, not invented at runtime.
    @dataclass
    class MultipleSchema(SampleSchema):
        fine: Mapping = SubpathMapping.path("fine")
        coarse: Mapping = SubpathMapping.path("coarse")

    class MultipleMapper(AnalysisMapper[MultipleSchema]):
        pass

    class MultipleAnalysis(SampleInput, Analysis[MultipleMapper]):
        def _get_output_subpaths(self, *, mapper):
            return (mapper.schema.fine, mapper.schema.coarse)

        def _compute_result(self, data, *, mapper, **kwargs):
            return {
                mapper.schema.coarse: data.data_source.isel(time=slice(None, None, 3)),
                mapper.schema.fine: data.data_source,
            }

    tree = MultipleAnalysis()(source)
    assert tree["example.sample/fine"].sizes["time"] == 12
    assert tree["example.sample/coarse"].sizes["time"] == 4
    assert not tree["example.sample"].dataset.variables


@pytest.mark.parametrize(
    ("namespace", "input_subpath"),
    [("_input", "_input"), ("_input/analysis", "_input"), ("_input", "_input/data")],
)
def test_invalid_installation_leaves_scope_unchanged(
    source, namespace, input_subpath, monkeypatch
):
    from dataclasses import replace

    schema = replace(
        SampleMapper.schema,
        namespace=SubpathMapping.path(namespace),
        input_subpath=SubpathMapping.path(input_subpath),
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    tree = xr.DataTree.from_dict(
        {input_subpath: source, "other": xr.Dataset({"value": 1})}
    )
    before = tree.copy(deep=False)
    monkeypatch.setattr(
        SampleAnalysis,
        "_compute_result",
        lambda *_args, **_kwargs: pytest.fail(
            "Invalid destinations must be rejected before computation"
        ),
    )
    with pytest.raises(ValueError):
        SampleAnalysis()(tree)
    xr.testing.assert_identical(tree, before)


def test_input_candidates_prefer_existing_domain_payload(source, monkeypatch):
    from dataclasses import replace

    schema = replace(
        SampleMapper.schema, input_subpath=SubpathMapping.path(("samples", "_input"))
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    tree = xr.DataTree.from_dict({"samples": source, "_input": source * 100})
    assert SampleAnalysis()(tree) is tree
    xr.testing.assert_identical(
        SampleView(tree).sample.drop_attrs(),
        source.isel(time=slice(None, None, 2)).drop_attrs(),
    )


def test_unwrap_validates_generated_scope_marker(source):
    from tollan.accessor.xarray import ensure_analysis_scope, unwrap_analysis_scope

    scope = ensure_analysis_scope(source)
    del scope["_input"]
    with pytest.raises(ValueError, match="Invalid analysis scope wrapper"):
        unwrap_analysis_scope(scope)
    scope = ensure_analysis_scope(source["values"])
    scope["_input"].attrs.clear()
    with pytest.raises(ValueError, match="DataArray wrapper marker"):
        unwrap_analysis_scope(scope)


def test_namespace_view_keeps_producing_config_with_selected_results(source):
    first = SampleAnalysis(step=2)
    tree = first(source)
    old_view = SampleView(tree)
    assert old_view._data_source is tree
    assert old_view.data_source is tree["example.sample"]
    assert old_view.sample_analysis is old_view.sample_analysis
    assert old_view.sample_analysis == first
    assert old_view.sample_analysis is not first
    old_data = old_view.sample
    second = SampleAnalysis(step=3)
    second(tree)
    new_view = SampleView(tree)
    assert new_view.sample_analysis == second
    assert old_view.sample_analysis == first
    assert old_view.data_source is not new_view.data_source
    xr.testing.assert_identical(old_view.sample, old_data)
    assert new_view.sample.sizes["time"] == 4


def test_configuration_comparison_uses_model_values(source):
    analysis = SampleAnalysis()
    tree = analysis(source)
    namespace = tree["example.sample"]
    namespace.attrs["example.sample.analysis"] = '{ "step" : 2 }'
    assert analysis(tree)["example.sample"] is namespace


def test_container_view_rejects_bare_dataset(source):
    with pytest.raises(TypeError, match="DataTree namespace"):
        SampleView(source)


def test_view_namespace_candidates_resolve_on_parent_scope(source, monkeypatch):
    from dataclasses import replace

    result = SampleAnalysis()(source)
    namespace = result["example.sample"].copy(deep=False)
    parent = xr.DataTree.from_dict({"diagnostics/sample": namespace})
    schema = replace(
        SampleMapper.schema,
        namespace=SubpathMapping.path(("absent", "diagnostics/sample")),
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    view = SampleView(parent)
    assert view.data_source is parent["diagnostics/sample"]
    assert view.sample_analysis == SampleAnalysis()


def test_installing_result_preserves_payload_metadata(source):
    key = "example.sample.analysis"
    source["values"].attrs[key] = "original variable metadata"
    source.attrs[key] = "original dataset metadata"
    result = SampleAnalysis()(source)
    assert source["values"].attrs[key] == "original variable metadata"
    assert source.attrs[key] == "original dataset metadata"
    view = SampleView(result)
    assert view.sample.attrs[key] == "original dataset metadata"
    assert view.sample["values"].attrs[key] == "original variable metadata"
    assert view.sample_analysis == SampleAnalysis()


@pytest.mark.parametrize("select_parent", [False, True])
def test_view_readability_does_not_require_a_writable_scope(select_parent):
    payload = xr.Dataset(
        {"value": 1},
        attrs={"example.sample.analysis": SampleAnalysis().model_dump_json()},
    )
    tree = xr.DataTree.from_dict({"example.sample": payload})
    supplied = tree if select_parent else tree["example.sample"]
    mapper = SampleMapper.from_data_source(supplied)
    assert mapper.get_namespace(supplied) is tree["example.sample"]
    assert SampleView(supplied).data_source is tree["example.sample"]


@pytest.mark.parametrize(
    ("first", "second"),
    [("sample", "sample"), ("sample", "sample/child"), ("sample/child", "sample")],
)
@pytest.mark.parametrize("force", [False, True])
def test_overlapping_outputs_fail_before_computation_or_reuse(
    source, first, second, force, monkeypatch
):
    @dataclass
    class MultipleSchema(SampleSchema):
        sample_subpath: SubpathMapping = SubpathMapping.path(first)
        other_subpath: SubpathMapping = SubpathMapping.path(second, resolve_value=True)

    class MultipleMapper(AnalysisMapper[MultipleSchema]):
        pass

    class MultipleAnalysis(SampleInput, Analysis[MultipleMapper]):
        def _get_output_subpaths(self, *, mapper):
            return (mapper.schema.sample_subpath, mapper.schema.other_subpath)

        def _compute_result(self, data, *, mapper, **kwargs):
            return {
                mapper.schema.sample_subpath: data.data_source,
                mapper.schema.other_subpath: data.data_source,
            }

    tree = SampleAnalysis()(source)
    before = tree.copy(deep=False)
    monkeypatch.setattr(
        MultipleAnalysis,
        "_compute_result",
        lambda *args, **kwargs: pytest.fail(
            "Invalid layout must fail before computing"
        ),
    )
    monkeypatch.setattr(
        MultipleAnalysis,
        "_load_from_attr",
        lambda *args, **kwargs: pytest.fail("Invalid layout must fail before reuse"),
    )
    with pytest.raises(ValueError, match="output subpaths must be separate"):
        MultipleAnalysis()(tree, force=force)
    xr.testing.assert_identical(tree, before)


def test_installation_rejects_inherited_dimension_without_altering_tree(
    source, monkeypatch
):
    from dataclasses import replace

    schema = replace(
        SampleMapper.schema, namespace=SubpathMapping.path("diagnostics/sample")
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    tree = xr.DataTree.from_dict(
        {"_input": source, "diagnostics": xr.Dataset({"v": ("sample", [1, 2])})}
    )
    before = tree.copy(deep=False)
    monkeypatch.setattr(
        SampleAnalysis,
        "_compute_result",
        lambda *_args, **_kwargs: pytest.fail(
            "Invalid namespaces must be rejected before computation"
        ),
    )
    with pytest.raises(ValueError, match="not an analysis scope"):
        SampleAnalysis()(tree)
    xr.testing.assert_identical(tree, before)


def test_namespace_creation_allows_scalar_data_in_parent(source, monkeypatch):
    from dataclasses import replace

    schema = replace(
        SampleMapper.schema, namespace=SubpathMapping.path("diagnostics/group/sample")
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    tree = xr.DataTree.from_dict(
        {
            "_input": source,
            "diagnostics": xr.Dataset({"scalar": 1}),
        }
    )
    analysis = SampleAnalysis()
    assert analysis(tree) is tree
    namespace = tree["diagnostics/group/sample"]
    assert analysis(tree) is tree
    assert tree["diagnostics/group/sample"] is namespace
    assert SampleView(tree).sample.sizes["time"] == 6
    assert tree["diagnostics"].dataset["scalar"].item() == 1


def test_namespace_validation_leaves_missing_and_existing_destinations_unchanged(
    source,
):
    from tollan.accessor.xarray.analysis import _validate_namespace_in_scope

    tree = xr.DataTree.from_dict(
        {
            "record/input": source,
            "record": xr.Dataset(attrs={"description": "record"}),
            "record/diagnostics": xr.Dataset({"scalar": 1}),
            "unrelated": xr.Dataset({"value": 2}),
        }
    )
    parent = tree["record"]
    input_node = parent["input"]
    unrelated = tree["unrelated"]
    before = tree.copy(deep=False)
    assert _validate_namespace_in_scope(parent, "diagnostics/analysis") is None
    xr.testing.assert_identical(tree, before)
    assert "analysis" not in parent["diagnostics"].children
    assert parent["input"] is input_node
    assert parent["input"].dataset["values"].data is source["values"].data
    assert parent["diagnostics"].dataset["scalar"].item() == 1
    assert parent.attrs == {"description": "record"}
    assert tree["unrelated"] is unrelated
    parent["diagnostics/analysis"] = xr.DataTree()
    namespace = parent["diagnostics/analysis"]
    namespace.attrs["configuration"] = "saved"
    namespace["output"] = xr.DataTree(dataset=source)
    before = tree.copy(deep=False)
    assert _validate_namespace_in_scope(parent, "diagnostics/analysis") is namespace
    assert namespace.attrs == {"configuration": "saved"}
    assert namespace["output"].dataset["values"].data is source["values"].data
    xr.testing.assert_identical(tree, before)


@pytest.mark.parametrize(
    "ancestor",
    [
        xr.Dataset(coords={"time": [0, 1]}),
        xr.Dataset(coords={"label": ("sample", [0, 1])}),
        xr.Dataset(coords={"reference": 1}),
        xr.Dataset({"signal": ("sample", [0, 1])}),
    ],
    ids=["index", "auxiliary-coordinate", "scalar-coordinate", "unindexed-dimension"],
)
@pytest.mark.parametrize("existing", [False, True])
def test_namespace_helper_rejects_inherited_context_without_creating_nodes(
    ancestor, existing
):
    from tollan.accessor.xarray.analysis import _validate_namespace_in_scope

    tree = xr.DataTree.from_dict({"selected/diagnostics": ancestor})
    selected = tree["selected"]
    if existing:
        selected["diagnostics/analysis"] = xr.DataTree()
    before = tree.copy(deep=False)
    with pytest.raises(ValueError, match="not an analysis scope"):
        _validate_namespace_in_scope(selected, "diagnostics/analysis")
    xr.testing.assert_identical(tree, before)
    assert tree["selected"] is selected


@pytest.mark.parametrize("namespace", ["payload/value", "payload/value/analysis"])
def test_namespace_helper_rejects_variable_paths_without_changing_tree(namespace):
    from tollan.accessor.xarray.analysis import _validate_namespace_in_scope

    tree = xr.DataTree.from_dict({"payload": xr.Dataset({"value": 1})})
    before = tree.copy(deep=False)
    with pytest.raises(TypeError):
        _validate_namespace_in_scope(tree, namespace)
    xr.testing.assert_identical(tree, before)


def test_failed_computation_leaves_no_prepared_namespace(source, monkeypatch):
    from dataclasses import replace

    schema = replace(
        SampleMapper.schema, namespace=SubpathMapping.path("diagnostics/new/analysis")
    )
    monkeypatch.setattr(SampleMapper, "schema", schema)
    tree = xr.DataTree.from_dict({"_input": source})
    before = tree.copy(deep=False)
    with pytest.raises(ValueError):
        SampleAnalysis(step=0)(tree)
    xr.testing.assert_identical(tree, before)
    assert "diagnostics" not in tree.children


@pytest.mark.parametrize("mismatch", ["missing", "extra", "replaced"])
def test_computed_output_mismatch_leaves_existing_results_unchanged(source, mismatch):
    class UndeclaredOutputAnalysis(SampleAnalysis):
        def _compute_result(self, data, *, mapper, **kwargs):
            outputs = super()._compute_result(data, mapper=mapper, **kwargs)
            if mismatch in {"missing", "replaced"}:
                outputs.pop(mapper.schema.sample_subpath)
            if mismatch in {"extra", "replaced"}:
                outputs[SubpathMapping.path("undeclared")] = data.data_source
            return outputs

    tree = SampleAnalysis()(source)
    before = tree.copy(deep=False)
    with pytest.raises(ValueError, match="Computed output fields must match"):
        UndeclaredOutputAnalysis()(tree, force=True)
    xr.testing.assert_identical(tree, before)


def test_unregistered_output_declaration_fails_before_computation(source):
    class InvalidLayoutAnalysis(SampleAnalysis):
        def _get_output_subpaths(self, *, mapper):
            return (SubpathMapping.path("undeclared"),)

        def _compute_result(self, data, *, mapper, **kwargs):
            pytest.fail("Unregistered fields must fail before computation")

    tree = SampleAnalysis()(source)
    before = tree.copy(deep=False)
    with pytest.raises(KeyError):
        InvalidLayoutAnalysis()(tree, force=True)
    xr.testing.assert_identical(tree, before)
