"""Configured analyses and result views for xarray DataTrees.

An analysis stores its output Datasets beneath a namespace. The namespace
attributes hold the configuration that produced those outputs. A result view
provides access to the outputs and the saved configuration.

The parent node is the analysis *scope*. A scope can contain attributes and
children, but must have no variables, coordinates, or dimensions, including
inherited ones. Output Datasets occupy separate descendants of the analysis
namespace, so each can use its own coordinates.

Examples
--------
Define a schema with paths for the analysis namespace and its output Dataset.
Paths are relative to the scope and namespace, respectively:

>>> from dataclasses import dataclass
>>> import numpy as np
>>> import xarray as xr
>>> from tollan.accessor import Mapping, NameMapping, SubpathMapping
>>> from tollan.accessor.xarray import (
...     Analysis, AnalysisMapper, AnalysisSchemaMixin, AnalysisView,
...     ensure_analysis_scope,
... )
>>> @dataclass
... class MeanSchema(AnalysisSchemaMixin):
...     namespace: SubpathMapping = SubpathMapping.path("example.mean")
...     analysis: Mapping = NameMapping.attr("example.mean.analysis")
...     mean_subpath: SubpathMapping = SubpathMapping.path("mean")
>>> class MeanMapper(AnalysisMapper[MeanSchema]):
...     pass

Implement the input-specific call and declare the output fields. The computation
returns a Dataset for each declared field:

>>> class MeanAnalysis(Analysis[MeanMapper]):
...     axis: int | None = None
...     def _get_output_subpaths(self, *, mapper):
...         return (mapper.schema.mean_subpath,)
...     def __call__(self, obj, *, output=None):
...         scope = ensure_analysis_scope(
...             xr.DataTree() if output is None else output)
...         mapper = self._mapper_cls.from_data_source(scope)
...         return self._call(
...             scope, mapper=mapper,
...             compute=lambda: {
...                 mapper.schema.mean_subpath: xr.Dataset({
...                     "mean": np.mean(obj, axis=self.axis)})},
...         )

Define view properties for the output and producing configuration:

>>> class MeanView(AnalysisView[MeanMapper, MeanAnalysis]):
...     @property
...     def mean_analysis(self):
...         return self._analysis_snapshot
...     @property
...     def mean(self):
...         return self.mapper.get_node(
...             self.data_source, self.mapper.schema.mean_subpath).to_dataset()
>>> analysis = MeanAnalysis()
>>> tree = analysis([1., 2., 3.])
>>> view = MeanView(tree)
>>> view.mean["mean"].item()
2.0
>>> view.mean_analysis == analysis
True
>>> view.data_source is tree["example.mean"]
True

To add results to an existing tree, select its working scope:

>>> enclosing = xr.DataTree.from_dict({"measurement": xr.Dataset()})
>>> scope = ensure_analysis_scope(enclosing, parent_namespace="measurement")
>>> analysis(np.arange(5.), output=scope) is scope
True

The analysis namespace contains both the outputs and their configuration. It can
be copied or exported independently:

>>> detached = MeanView(scope).data_source.copy(deep=False)
>>> MeanView(detached).mean["mean"].item()
2.0

For analyses that retain their xarray input, prepare an input view. A DataArray
or Dataset is stored at ``_input`` in a new scope, sharing its array storage:

>>> from tollan.accessor.xarray import (
...     AnalysisInputMapper, AnalysisInputSchema, AnalysisInputView,
...     prepare_analysis_input_view,
... )
>>> array = xr.DataArray([1., 2., 3.], dims="sample", name="signal")
>>> input_view = prepare_analysis_input_view(array)
>>> input_view.data_source.path
'/_input'
>>> input_view.data_source["signal"].data is array.data
True
>>> input_view.unwrap().identical(array)
True

An input schema can select an existing subtree. Candidates are tried in order;
``_input`` also allows this view to read automatically prepared inputs:

>>> @dataclass
... class SamplesInputSchema(AnalysisInputSchema):
...     input_subpath: SubpathMapping = SubpathMapping.path(("samples", "_input"))
>>> class SamplesInputMapper(AnalysisInputMapper[SamplesInputSchema]):
...     pass
>>> class SamplesInputView(AnalysisInputView[SamplesInputMapper]):
...     pass
>>> enclosing = xr.DataTree.from_dict({"measurement/samples": array.to_dataset()})
>>> selected = prepare_analysis_input_view(
...     enclosing, view_cls=SamplesInputView, parent_namespace="measurement")
>>> selected.data_source is enclosing["measurement/samples"]
True
>>> selected.unwrap() is enclosing["measurement"]
True

Notes
-----
Recomputation replaces the analysis namespace and its descendants. Existing
result views retain their selected namespace and producing configuration;
construct a new view to read the replacement results.

Scope preparation shares arrays without loading them. The computation supplied
by each analysis determines whether its outputs are eager or lazy.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from itertools import combinations
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Self, overload

import xarray as xr

from tollan.config import FrozenBaseModel
from tollan.utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)

from ..accessor import AccessorBase
from ..schema import Mapping, Schema, SubpathMapping
from .mapper import XarrayMapper
from .utils import XarraySourceT, ensure_datatree, unwrap_data_source

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping as MappingABC

__all__ = [
    "Analysis",
    "AnalysisInputMapper",
    "AnalysisInputSchema",
    "AnalysisInputView",
    "AnalysisMapper",
    "AnalysisSchemaMixin",
    "AnalysisView",
    "ensure_analysis_scope",
    "prepare_analysis_input_view",
    "unwrap_analysis_scope",
]

_SCOPE_WRAPPER_ATTR = "_tollan_accessor_xarray_analysis_input_type"
_INPUT_SUBPATH = "_input"


def _namespace_is_scope(namespace: xr.DataTree) -> bool:
    """Return whether a node has no local payload or inherited constraints."""
    return (
        not namespace.sizes and not namespace.to_dataset(inherit="all_coords").variables
    )


def _validate_namespace_in_scope(
    scope: xr.DataTree, namespace: str
) -> xr.DataTree | None:
    """Check whether an analysis namespace can hold output subtrees.

    Parameters
    ----------
    scope : xarray.DataTree
        Valid analysis scope containing the destination.
    namespace : str
        Relative descendant path validated by ``SubpathMapping``.

    Returns
    -------
    xarray.DataTree or None
        The existing destination, or ``None`` if it can be created. The supplied
        tree is unchanged.

    Raises
    ------
    ValueError
        The destination would have variables, coordinates, or dimensions.
    TypeError
        The path identifies or traverses a variable.
    """
    try:
        existing = scope[namespace]
    except KeyError:
        existing = None
    except AttributeError as error:
        # xarray lookup calls .get() on an intermediate DataArray in this case.
        msg = "A namespace path must traverse DataTree nodes, not variables"
        raise TypeError(msg) from error

    target = existing
    if target is None:
        candidate = xr.DataTree()
        branch = candidate
        source = scope
        for part in namespace.split("/"):
            if part not in source.children:
                break
            source = source.children[part]
            branch[part] = xr.DataTree(dataset=source.to_dataset(inherit=False))
            branch = branch[part]
        candidate[namespace] = xr.DataTree()
        target = candidate[namespace]

    if not isinstance(target, xr.DataTree):
        msg = "The analysis namespace must identify a DataTree node"
        raise TypeError(msg)
    if not _namespace_is_scope(target):
        msg = (
            f"Namespace {target.path!r} is not an analysis scope: "
            "it has variables, coordinates, or dimensions"
        )
        raise ValueError(msg)
    return target if existing is not None else None


def ensure_analysis_scope(
    data: XarraySourceT,
    *,
    parent_namespace: str | None = None,
) -> xr.DataTree:
    """Select or create a DataTree scope for analysis results.

    Parameters
    ----------
    data : xarray.DataArray, xarray.Dataset, or xarray.DataTree
        Input to retain, or tree containing an existing scope.
    parent_namespace : str, optional
        Scope path within a DataTree. Relative paths start at the supplied node;
        absolute paths start at the tree root. If omitted, use the supplied node.
        Omit for DataArray and Dataset inputs.

    Returns
    -------
    xarray.DataTree
        For a DataTree, the selected node with its parent and children retained.
        For a DataArray or Dataset, a new scope containing the input at ``_input``
        with shared array storage. Use ``unwrap_analysis_scope`` to recover it.

    Raises
    ------
    TypeError
        The input type is unsupported, a path is supplied for a DataArray or
        Dataset, or the path identifies a variable.
    KeyError
        The selected path does not exist.
    ValueError
        The selected scope has variables, coordinates, or dimensions, including
        inherited coordinates and dimensions.
    """
    if isinstance(data, xr.DataTree):
        scope = data if parent_namespace is None else data[parent_namespace]
        if not isinstance(scope, xr.DataTree):
            msg = "The parent namespace must identify a DataTree node"
            raise TypeError(msg)
        if not _namespace_is_scope(scope):
            msg = (
                f"Namespace {scope.path!r} is not an analysis scope: "
                "it has variables, coordinates, or dimensions"
            )
            raise ValueError(msg)
        return scope
    if parent_namespace is not None:
        msg = "Selecting a parent namespace requires a DataTree"
        raise TypeError(msg)
    input_tree = ensure_datatree(data)
    kind = "dataarray" if isinstance(data, xr.DataArray) else "dataset"
    scope = xr.DataTree(dataset=xr.Dataset(attrs={_SCOPE_WRAPPER_ATTR: kind}))
    scope[_INPUT_SUBPATH] = input_tree
    return scope


def unwrap_analysis_scope(scope: xr.DataTree) -> XarraySourceT:
    """Recover input retained by ``ensure_analysis_scope``.

    Parameters
    ----------
    scope : xarray.DataTree
        Prepared analysis scope.

    Returns
    -------
    xarray.DataArray, xarray.Dataset, or xarray.DataTree
        The retained DataArray or Dataset when the scope was created from one,
        sharing its array storage. An unnamed DataArray has the name ``data``.
        Analysis results are excluded from the recovered input. For a scope
        selected from an existing tree, return that node with all its children.

    Raises
    ------
    TypeError
        The supplied object is not a DataTree.
    ValueError
        The stored input or its container metadata is invalid.
    """
    if not isinstance(scope, xr.DataTree):
        msg = "An analysis scope must be a DataTree"
        raise TypeError(msg)
    if _SCOPE_WRAPPER_ATTR not in scope.attrs:
        return scope
    kind = scope.attrs[_SCOPE_WRAPPER_ATTR]
    if kind not in ("dataset", "dataarray") or _INPUT_SUBPATH not in scope.children:
        msg = "Invalid analysis scope wrapper"
        raise ValueError(msg)
    payload = scope[_INPUT_SUBPATH].to_dataset()
    if kind == "dataset":
        return payload
    result = unwrap_data_source(payload)
    if not isinstance(result, xr.DataArray):
        msg = "Analysis scope input is missing its DataArray wrapper marker"
        raise ValueError(msg)  # noqa: TRY004 - corrupt wrapper metadata
    return result


@dataclass
class AnalysisInputSchema(Schema):
    """Schema for locating input within an analysis scope.

    Attributes
    ----------
    input_subpath : SubpathMapping
        Input path relative to the scope. Defaults to ``_input``, the location
        used by ``ensure_analysis_scope`` for DataArray and Dataset inputs.
    """

    input_subpath: SubpathMapping = SubpathMapping.path(_INPUT_SUBPATH)


class AnalysisInputMapper[SchemaT: AnalysisInputSchema = AnalysisInputSchema](
    XarrayMapper[SchemaT]
):
    """Mapper for input subtrees within an analysis scope."""

    def get_input_node(self, scope: xr.DataTree) -> xr.DataTree:
        """Return the mapped input subtree.

        Parameters
        ----------
        scope : xarray.DataTree
            Scope used to resolve this mapper's input path.

        Returns
        -------
        xarray.DataTree
            Selected node with its parent and children retained.

        Raises
        ------
        KeyError
            The mapped path does not identify a tree node.
        """
        return self.get_node(scope, self.schema.input_subpath)


class AnalysisInputView[MapperT: AnalysisInputMapper = AnalysisInputMapper](
    AccessorBase[xr.DataTree, MapperT]
):
    """View of an input subtree within an analysis scope.

    Parameters
    ----------
    data_source : xarray.DataTree
        Working scope containing the mapped input subtree.
    mapper : AnalysisInputMapper, optional
        Input mappings resolved against the scope. If omitted, resolve the
        view's mapper class against the supplied scope.

    Raises
    ------
    TypeError
        The source is not a DataTree.
    ValueError
        The scope has variables, coordinates, or dimensions, including inherited
        coordinates and dimensions.
    KeyError
        The mapped input subtree does not exist.

    See Also
    --------
    prepare_analysis_input_view : Prepare a scope and construct an input view.

    Notes
    -----
    ``data_source`` is the selected input node; ``_data_source`` retains the
    supplied scope. Subclasses can validate the selected input by extending
    ``_validate`` and calling ``super()._validate()`` first.
    """

    @cached_property
    def data_source(self) -> xr.DataTree:
        """Input subtree selected within the supplied scope."""
        return self.mapper.get_input_node(self._data_source)

    def unwrap(self) -> XarraySourceT:
        """Return the retained DataArray, Dataset, or existing tree scope.

        Returns
        -------
        xarray.DataArray, xarray.Dataset, or xarray.DataTree
            Input recovered by ``unwrap_analysis_scope`` from the view's scope.
            DataArray and Dataset inputs share their original array storage; an
            unnamed array has the name ``data``. An existing tree scope is returned
            with all its children, including analysis results.

        Raises
        ------
        ValueError
            The stored input or its container metadata is invalid.
        """
        return unwrap_analysis_scope(self._data_source)

    def _validate(self) -> None:
        if not isinstance(self._data_source, xr.DataTree):
            msg = "An analysis input view requires a DataTree scope"
            raise TypeError(msg)
        if not _namespace_is_scope(self._data_source):
            msg = "The supplied node is not an analysis scope"
            raise ValueError(msg)
        _ = self.data_source


@overload
def prepare_analysis_input_view(
    data: XarraySourceT,
    *,
    parent_namespace: str | None = None,
) -> AnalysisInputView: ...


@overload
def prepare_analysis_input_view[ViewT: AnalysisInputView](
    data: XarraySourceT,
    *,
    view_cls: type[ViewT],
    parent_namespace: str | None = None,
) -> ViewT: ...


def prepare_analysis_input_view(
    data: XarraySourceT,
    *,
    view_cls: type[AnalysisInputView] = AnalysisInputView,
    parent_namespace: str | None = None,
) -> AnalysisInputView:
    """Prepare a scope and return a view of its input subtree.

    Parameters
    ----------
    data : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Input to retain at ``_input``, or tree containing the working scope.
    view_cls : type of AnalysisInputView, default AnalysisInputView
        View class whose mapper selects the input subtree.
    parent_namespace : str, optional
        Scope path within a DataTree. Relative paths start at the supplied node;
        absolute paths start at the tree root. Defaults to the supplied node.
        Omit for DataArray and Dataset inputs.

    Returns
    -------
    AnalysisInputView
        View whose ``data_source`` is the selected input node. The prepared
        scope is retained in ``_data_source``. Use ``unwrap()`` to recover the
        retained DataArray or Dataset, or the selected scope of an existing tree.

    Raises
    ------
    TypeError
        The input type is unsupported, a path is supplied for a DataArray or
        Dataset, or the path identifies a variable.
    ValueError
        The selected scope has variables, coordinates, or dimensions, including
        inherited coordinates and dimensions.
    KeyError
        The selected scope or mapped input subtree does not exist.
    """
    scope = ensure_analysis_scope(data, parent_namespace=parent_namespace)
    return view_cls(scope)


@dataclass
class AnalysisSchemaMixin(Schema):
    """Schema fields for an analysis namespace and its configuration.

    Attributes
    ----------
    namespace : SubpathMapping
        Analysis namespace relative to the working scope.
    analysis : Mapping
        Attribute containing the JSON configuration on the analysis namespace.

    Notes
    -----
    Subclasses declare a ``SubpathMapping`` field for each output Dataset,
    relative to ``namespace``. Output paths must occupy separate subtrees.
    """

    namespace: SubpathMapping
    analysis: Mapping


class AnalysisMapper[SchemaT: AnalysisSchemaMixin](XarrayMapper[SchemaT]):
    """Namespace selection within an analysis scope."""

    def get_namespace(self, data: xr.DataTree) -> xr.DataTree:
        """Return the analysis namespace identified by this mapper.

        Parameters
        ----------
        data : xarray.DataTree
            Analysis namespace or its enclosing working scope.

        Returns
        -------
        xarray.DataTree
            The supplied node if it contains the mapped configuration attribute;
            otherwise, the node at the mapped namespace path. Its parent and
            children are retained.

        Raises
        ------
        TypeError
            The supplied source is not a DataTree.
        ValueError
            Neither the configuration attribute nor the namespace path is present.
        """
        if not isinstance(data, xr.DataTree):
            msg = "An analysis container view requires a DataTree namespace"
            raise TypeError(msg)
        if self.has_attr(data, self.schema.analysis):
            node = data
        elif self.has_node(data, self.schema.namespace):
            node = self.get_node(data, self.schema.namespace)
        else:
            msg = "No analysis namespace found"
            raise ValueError(msg)
        return node


class Analysis[MapperT: AnalysisMapper](FrozenBaseModel):
    """Configuration base for analyses with DataTree outputs.

    Notes
    -----
    Subclass ``Analysis[ConcreteMapper]`` and declare configuration fields as
    model fields. Implement ``_get_output_subpaths`` to return the schema fields
    for the output Datasets.

    The subclass's ``__call__`` validates its inputs, prepares a scope with
    ``ensure_analysis_scope``, and resolves a mapper with
    ``self._mapper_cls.from_data_source(scope)``. It then calls ``self._call``
    with that scope, mapper, and a computation returning Datasets keyed by the
    declared output fields. A ``can_reuse`` callback can validate existing results
    when the saved configuration matches.

    Each result namespace stores its producing configuration as JSON at the
    schema's ``analysis`` attribute. ``AnalysisView`` restores that configuration
    as an instance of the analysis class.
    """

    _mapper_cls: ClassVar

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Infer the output mapper class from the concrete generic binding."""
        super().__pydantic_init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            Analysis,
            MapperT=GenericBindingRequirement("_mapper_cls", AnalysisMapper),
        )
        if bindings is not None:
            cls._mapper_cls = bindings["MapperT"]

    def _dump_to_attr(self, data_source: XarraySourceT, *, mapper: MapperT) -> None:
        """Write this configuration to the mapped attribute.

        Parameters
        ----------
        data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
            Object whose attributes will receive the JSON configuration.
        mapper : AnalysisMapper
            Mapper identifying the ``analysis`` attribute.

        Returns
        -------
        None
            Updates the supplied object's attribute in place.
        """
        name = mapper.mapped_fields[mapper.schema.analysis].name
        data_source.attrs[name] = self.model_dump_json()

    @classmethod
    def _load_from_attr(
        cls, data_source: XarraySourceT, *, mapper: MapperT
    ) -> Self | None:
        """Read this analysis configuration from the mapped attribute.

        Parameters
        ----------
        data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
            Object containing the configuration in its own attributes.
        mapper : AnalysisMapper
            Mapper identifying the ``analysis`` attribute.

        Returns
        -------
        Self or None
            Reconstructed configuration, or ``None`` if the attribute is absent.

        Raises
        ------
        ValueError
            The attribute is not valid JSON or fails model validation.
        """
        name = mapper.mapped_fields[mapper.schema.analysis].name
        if name not in data_source.attrs:
            return None
        return cls.model_validate_json(data_source.attrs[name])

    def _get_output_subpaths(self, *, mapper: MapperT) -> tuple[SubpathMapping, ...]:
        """Return the schema fields for this configuration's output Datasets.

        Parameters
        ----------
        mapper : AnalysisMapper
            Mapper resolved against the output scope.

        Returns
        -------
        tuple of SubpathMapping
            Fields identifying all output Datasets relative to the analysis
            namespace. The computation must return exactly these fields as keys.

        Notes
        -----
        Subclasses implement this hook. It runs before computation and reuse checks,
        so it must determine the output layout without computing results.
        """
        raise NotImplementedError

    def _call(
        self,
        scope: xr.DataTree,
        *,
        mapper: MapperT,
        compute: Callable[[], MappingABC[SubpathMapping, xr.Dataset]],
        can_reuse: Callable[[xr.DataTree], bool] | None = None,
        force: bool = False,
    ) -> xr.DataTree:
        """Compute or reuse results in a prepared analysis scope.

        Parameters
        ----------
        scope : xarray.DataTree
            Output scope validated by ``ensure_analysis_scope``.
        mapper : AnalysisMapper
            Mapper identifying the namespace, output paths, and configuration attribute.
        compute : callable
            Zero-argument function returning Datasets keyed by the fields from
            ``_get_output_subpaths``. It must leave existing inputs and results
            unchanged.
        can_reuse : callable, optional
            Function receiving an existing result namespace and returning whether
            it is reusable. Called only when its saved configuration matches and
            ``force`` is False. If omitted, recompute.
        force : bool, default False
            Recompute regardless of existing results.

        Returns
        -------
        xarray.DataTree
            The supplied scope. Newly computed outputs replace the complete analysis
            namespace, including descendants, while retaining unrelated branches.

        Raises
        ------
        ValueError
            The destination namespace is invalid, output paths overlap, the saved
            configuration is invalid, or returned output fields differ from the
            declaration.
        KeyError
            A declared output field is not registered in the mapper.

        Notes
        -----
        Destination and output-path validation precede the reuse and computation
        callbacks. Results are installed after successful computation and assembly;
        failures leave the existing namespace unchanged. Lazy arrays remain lazy.
        """
        fields = self._get_output_subpaths(mapper=mapper)
        paths = [mapper.mapped_fields[field].name for field in fields]
        self._validate_output_subpaths(paths)
        namespace = mapper.mapped_fields[mapper.schema.namespace].name
        saved = _validate_namespace_in_scope(scope, namespace)
        if not force and saved is not None:
            config = self._load_from_attr(saved, mapper=mapper)
            if (
                config is not None
                and config == self
                and can_reuse is not None
                and can_reuse(saved)
            ):
                return scope
        outputs = compute()
        if outputs.keys() != set(fields):
            msg = "Computed output fields must match the declared output subpaths"
            raise ValueError(msg)
        result_tree = xr.DataTree()
        for field, path in zip(fields, paths, strict=True):
            result_tree[path] = xr.DataTree(dataset=outputs[field])
        self._dump_to_attr(result_tree, mapper=mapper)
        scope[namespace] = result_tree
        return scope

    @staticmethod
    def _validate_output_subpaths(output_subpaths: list[str]) -> None:
        """Require the declared output Datasets to occupy separate leaves."""
        output_paths = [PurePosixPath(path) for path in output_subpaths]
        for left, right in combinations(output_paths, 2):
            if left.is_relative_to(right) or right.is_relative_to(left):
                msg = "Analysis output subpaths must be separate subtrees"
                raise ValueError(msg)


class AnalysisView[MapperT: AnalysisMapper, AnalysisT: Analysis](
    AccessorBase[xr.DataTree, MapperT]
):
    """View of analysis outputs and their producing configuration.

    Parameters
    ----------
    data_source : xarray.DataTree
        Analysis namespace or its enclosing working scope.
    mapper : AnalysisMapper, optional
        Namespace and output mappings. If omitted, resolve the view's mapper
        class against the supplied tree.

    Raises
    ------
    TypeError
        The supplied source is not a DataTree.
    ValueError
        The namespace or its configuration is absent, or the configuration is
        invalid for the analysis class.

    Notes
    -----
    Subclass ``AnalysisView[ConcreteMapper, ConcreteAnalysis]`` and expose output
    properties through the mapped subpaths. ``data_source`` is the selected
    analysis namespace; ``_data_source`` retains the supplied tree. A property
    such as ``mean_analysis`` can return the typed ``_analysis_snapshot``.

    The view retains its namespace and configuration after a later analysis
    replaces them. Construct a new view to read the new results. Subclasses that
    override ``_validate`` must call ``super()._validate()`` first.
    """

    _analysis_cls: ClassVar

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Infer the producing analysis class from its concrete generic binding."""
        super().__init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            AnalysisView,
            AnalysisT=GenericBindingRequirement("_analysis_cls", Analysis),
        )
        if bindings is not None:
            cls._analysis_cls = bindings["AnalysisT"]

    @cached_property
    def data_source(self) -> xr.DataTree:
        """Analysis namespace selected from the supplied tree."""
        return self.mapper.get_namespace(self._data_source)

    @cached_property
    def _analysis_snapshot(self) -> AnalysisT:
        """Producing configuration captured when this view is validated."""
        analysis = self._analysis_cls._load_from_attr(
            self.data_source, mapper=self.mapper
        )
        if analysis is None:
            msg = "Missing producing analysis configuration"
            raise ValueError(msg)
        return analysis

    def _validate(self) -> None:
        _ = self._analysis_snapshot
