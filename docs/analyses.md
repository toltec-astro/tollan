# Analyses and results

Compute results with an `Analysis`, then read the results and their producing
settings through an `AnalysisView`.

| Task | Example |
| --- | --- |
| Define a calculation and its result view | [Compute a mean](#computation-and-producing-configuration) |
| Keep an input available alongside results | [Retain and recover xarray input](#retain-and-recover-xarray-input) |
| Read saved results and their settings | [Read results](#read-results) |
| Add or replace results in a shared tree | [Add results to an existing tree](#add-results-to-an-existing-tree) |

(store-analysis-results-in-a-datatree)=
## Computation and producing configuration

An analysis writes its output Datasets beneath a namespace and saves its
configuration in that namespace's attributes. Each output Dataset can have its
own coordinates. A view reads the outputs and their producing configuration.

Define the namespace, configuration attribute, and output paths in a schema.
Implement the computation in an `Analysis` subclass and expose the results
through an `AnalysisView`:

```{testcode}
from dataclasses import dataclass

import numpy as np
import xarray as xr
from tollan.accessor import Mapping, NameMapping, SubpathMapping
from tollan.accessor.xarray import (
    Analysis,
    AnalysisMapper,
    AnalysisSchemaMixin,
    AnalysisView,
    ensure_analysis_scope,
)


@dataclass
class MeanSchema(AnalysisSchemaMixin):
    _namespace: SubpathMapping = SubpathMapping.path("example.mean")
    analysis: NameMapping = NameMapping.attr("example.mean.analysis")
    mean_subpath: SubpathMapping = SubpathMapping.path("mean")


class MeanMapper(AnalysisMapper[MeanSchema]):
    pass


class MeanAnalysis(Analysis[MeanMapper]):
    axis: int | None = None

    def _get_output_subpaths(self, *, mapper):
        return (mapper.schema.mean_subpath,)

    def __call__(self, obj, *, output=None):
        scope = xr.DataTree() if output is None else output
        mapper = self._mapper_cls.from_data_source(scope)
        return self._call(
            scope,
            mapper=mapper,
            compute=lambda: {
                mapper.schema.mean_subpath: xr.Dataset({
                    "mean": np.mean(obj, axis=self.axis)
                })
            },
        )


class MeanView(AnalysisView[MeanMapper, MeanAnalysis]):
    @property
    def mean_analysis(self):
        return self._analysis_snapshot

    @property
    def mean(self):
        return self.mapper.get_node(
            self.data_source, self.mapper.schema.mean_subpath
        ).to_dataset()


analysis = MeanAnalysis()
result = analysis([1.0, 2.0, 3.0])
view = MeanView(result)
assert view.mean["mean"].item() == 2.0
assert view.mean_analysis == analysis
assert view.data_source is result["example.mean"]
```

The result has this layout:

```text
/                         working scope
└── example.mean          attrs: saved analysis configuration
    └── mean              Dataset containing the mean variable
```

The concrete schema must define `_namespace` as a `SubpathMapping` relative to
the working scope. Output subpaths are relative to the analysis namespace and
must occupy separate subtrees. Use `SubpathMapping.path()` for these fields.
`_get_output_subpaths()` declares the outputs before computation; the computation
returns Datasets keyed by a subset or all of these fields.

(read-results)=
## Result views

### Read results

Construct a result view from the working scope, or use
`MeanView.from_namespace(node)` for an explicitly selected analysis namespace.
Its `data_source` is the selected namespace, and its configuration property
returns the producing analysis. Treat the bound source as read-only while using
the view; create a new view after replacing the results.

A view can also read a detached namespace:

```{testcode}
detached = view.data_source.copy(deep=False)
detached_view = MeanView.from_namespace(detached)
xr.testing.assert_identical(detached_view.mean, view.mean)
assert detached_view.mean_analysis == analysis
```

## Inputs and output scopes

### Retain and recover xarray input

Use `prepare_analysis_input_view()` to retain a DataArray or Dataset under
`_input` in a new scope. The view's `data_source` selects that input node, and
`unwrap()` recovers the original container type:

```{testcode}
import xarray as xr
from tollan.accessor.xarray import prepare_analysis_input_view

signal = xr.DataArray([1.0, 2.0, 3.0], dims="sample", name="signal")
input_view = prepare_analysis_input_view(signal)
assert input_view.data_source.path == "/_input"
assert input_view.data_source["signal"].data is signal.data
assert input_view.unwrap().identical(signal)
```

An unnamed DataArray is stored and recovered with the name `data`. Array storage
is shared. For an existing tree, `parent_namespace` selects the scope, and
`unwrap()` returns that scope with its children and results.

Subclass `AnalysisInputSchema`, `AnalysisInputMapper`, and `AnalysisInputView` to
select an input at another path. Set `input_subpath` to an ordered list of
candidates, such as `SubpathMapping.path(("samples", "_input"))`, and pass the view
class as `view_cls=`. The view retains its prepared scope in `_data_source` for
analysis code to use as the output scope. The
`tollan.accessor.xarray.analysis` module examples show this
input-selection pattern.

## Result reuse and replacement

(add-results-to-an-existing-tree)=
### Add results to an existing tree

Select a working scope with `ensure_analysis_scope()`. A valid scope has no
coordinates or dimensions, including inherited ones. It can contain scalar data
variables, attributes, and child nodes. Several analyses can share this scope by selecting
distinct namespaces; input subtrees and sibling analysis results stay in place:

```{testcode}
tree = xr.DataTree.from_dict({"measurement": xr.Dataset()})
scope = ensure_analysis_scope(tree, parent_namespace="measurement")
assert analysis([2.0, 4.0], output=scope) is scope
assert MeanView(tree["measurement"]).mean["mean"].item() == 3.0
```

`_call()` checks the destination and output paths before computation. Successful
computation assembles a complete namespace and then replaces the previous
namespace, including partial results, while retaining sibling analyses and input
branches. A failed computation leaves existing results unchanged.

To reuse results, pass a `can_reuse` callback to `_call()`. It receives the
existing namespace when its saved configuration equals the current configuration.
Return `True` when the results are suitable for the supplied inputs. With no
callback, or with `force=True`, the analysis recomputes. Configuration equality
alone does not establish that input values are unchanged.

## Read saved results and producing settings

Save the namespace with xarray, then construct the same view on the reopened
data. The namespace already contains the producing configuration; you do not
need a separate configuration dump:

```{testcode}
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory() as directory:
    store = Path(directory) / "mean.zarr"
    view.data_source.to_zarr(store)
    with xr.open_datatree(store, engine="zarr") as reopened:
        restored = MeanView.from_namespace(reopened)
        xr.testing.assert_identical(restored.mean, view.mean)
        assert restored.mean_analysis == analysis
```

Use the reopened view's `mean_analysis` property to inspect the settings without
rerunning the calculation or loading its original pipeline invocation.

When running an analysis inside a pipeline step, use the analysis view for
scientific results and producing settings. Use the step context for invocation
status, failures, and published payloads. Follow the
[context export example](pipelines.md#recreate-a-step-or-restore-exported-context)
to include those invocation fields in a product as well.
