# Steps and pipelines

Run configured operations on a shared working data container and inspect each
operation's state and results. `SequentialPipeline` runs enabled steps in the
order you supply; arrange required producers before their consumers. The step
and context interfaces do not require this driver and can be used by other
orchestrators.

| Need | Use |
| --- | --- |
| Validate a step's settings | A `StepConfig` subclass |
| Record settings, completion, and failures | A `StepContext` subclass |
| Publish a view or a bundle of results for downstream steps | A typed `context.data` field on that subclass |
| Retain configured figures or other artifacts for export | [`context.artifacts` and artifact specs](artifacts.md) |
| Read scientific results from the working container | A result view using a schema and mapper |
| Record failures during an operation | Append `StepFailure` instances to `context.failures` |
| Run an operation and record its invocation | A `Step` subclass implementing `run()` |
| Reuse a calculation independently of step execution | [Step operations and numerical methods](#reuse-step-operations-and-computations) |
| Run enabled steps in order | `SequentialPipeline` |
| Export selected context fields | `Step.dump_context()` and a product writer |
| Export result datasets with their producing configuration | [xarray analyses](analyses.md#computation-and-producing-configuration) |

(define-and-run-a-step)=
## Define and invoke a step

1. Declare settings on a `StepConfig` subclass.
2. Define a `StepContext` subclass with a typed `data` field for the results
   downstream steps need. Leave it as None if no payload is needed.
3. Bind both to a `Step` and implement `run(data, context)`.
4. Call the step or add it to a `SequentialPipeline`.

Step settings are read-only and validated strictly, including declared defaults.
Pass numeric and boolean values directly rather than as strings. `StepConfig`
also provides `model_dump_yaml()` and `model_validate_yaml()` for saving and
loading settings. Invocation contexts remain mutable while a step runs.

```{graphviz}
digraph step {
    rankdir=LR;
    node [shape=box];
    StepConfig -> Step [label="settings"];
    Step -> StepContext [label="creates per call"];
    Step -> "data container" [label="run()"];
    "data container" -> StepContext [label="get_context()"];
    "result view" -> "data container" [label="reads products"];
}
```

### Keep input and result datasets in the working tree

This example scales a signal into a new dataset. The input remains in `raw`;
the step writes `scaled`. Only the leaf nodes carry arrays, so each dataset can
use its own coordinates. The root holds the invocation contexts:

```text
/                               working DataTree
├── attrs["__pipeline_context__"]
│   └── Scale.context_key        ScaleContext
│       ├── config.factor       3.0
│       ├── data                ScaleView → scaled Dataset
│       ├── completed           True
│       └── failures            []
├── raw                         Dataset: signal(sample) = [1.0, 2.0]
└── scaled                      Dataset: signal(sample) = [3.0, 6.0]
```

`raw` and `scaled` are paths chosen for this example, not paths required by
Tollan. The schema and mapper give the step and view access to both signals:

```{literalinclude} examples/pipeline_example.py
:language: python
:start-at: from __future__ import annotations
:end-before: class ScaleConfig
```

The step installs the result in the supplied tree and publishes a view of that
result through `context.data`. The view shares the result's array storage.
`arbitrary_types_allowed=True` permits the view as a Pydantic field;
`exclude=True` omits it from model dumps while preserving it in pickle:

```{literalinclude} examples/pipeline_example.py
:language: python
:start-at: class ScaleConfig
:end-before: class WriteSignalConfig
```

Save the {download}`complete example <examples/pipeline_example.py>` as `pipeline_example.py`
in your Python import path, then run it on a tree:

```{testcode}
import xarray as xr
from pipeline_example import Scale, ScaleContext, ScaleView, WriteSignal
from tollan.pipeline import (
    PIPELINE_CONTEXT_KEY,
    SequentialPipeline,
    Step, StepConfig, StepContext,
    StepFailure, StepFailureKind,
)

source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
tree = xr.DataTree.from_dict({"raw": source})
pipeline = SequentialPipeline(steps=[Scale(factor=3.0)])
assert pipeline(tree) is tree
assert source["signal"].values.tolist() == [1.0, 2.0]
assert tree["raw"].to_dataset().identical(source)
context = Scale.get_context(tree)
assert tree.attrs[PIPELINE_CONTEXT_KEY][Scale] is context
assert context.completed
assert context.data.signal.values.tolist() == [3.0, 6.0]
assert context.data.signal.data is tree["scaled/signal"].data
assert context.config.factor == 3.0
```

Steps may also update an existing dataset in place. The concrete step determines
which inputs it preserves and which products it replaces. For a computation
with its own configuration and multiple result datasets, use an
[xarray analysis](analyses.md#computation-and-producing-configuration) inside
`run()` and expose its products through the analysis view.

Construct a step with a configuration model, keyword settings, or both.
Keywords override a supplied model's values and are validated again. The step
and context must bind the same configuration type.

| Operation | Result |
| --- | --- |
| `step(source)` | Runs the step; replaces its previous context. |
| `step(source, return_context=True)` | Returns `(source, context)`. |
| `run()` finishes without failures | Marks the context complete; the pipeline continues. |
| `run()` finishes with failures | Leaves the context incomplete; the pipeline continues. |
| `run()` raises an `Exception` | Appends its message and class name to `context.failures`, then re-raises; prior mutations remain. |
| `Step.get_context(source)` before execution | Raises `KeyError`. |

Context lookup, including `has_context()`, attaches an empty context store when
the container has none.

### Reuse step operations and computations

Choose between the complete invocation, an operation with an explicit context,
and numerical computation:

| Level | Call | Result |
| --- | --- | --- |
| High: complete invocation | `Scale(factor=3.0)(tree)` | Updated working tree, attached context, and completion or failure record |
| Middle: domain integration | `Scale.run(tree, context)` | Updated tree and payload using the supplied context; no automatic lifecycle handling |
| Low: numerical computation | `Scale.compute_scaled(values, factor=3.0)` | Numerical array using explicit parameters |

Use `run()` when you already have the working data and context. It needs no
configured step instance. The caller owns context attachment, completion, and
exception recording. The method is a classmethod because the step protocol
supplies settings and invocation state through `context`:

```{testcode}
from pipeline_example import ScaleConfig

working = xr.DataTree.from_dict({
    "raw": xr.Dataset({"signal": ("sample", [1.0, 2.0])})
})
operation_context = ScaleContext(step_cls=Scale, config=ScaleConfig(factor=3.0))
Scale.run(working, operation_context)
assert operation_context.data.signal.values.tolist() == [3.0, 6.0]
assert not operation_context.completed
assert PIPELINE_CONTEXT_KEY not in working.attrs
```

`run()` combines computations, selects inputs, installs results, and publishes
invocation data. It can pass parameters from `context.config` to numerical
routines or call a configured analysis. Both `run()` and an analysis's configured
recipes serve the middle level; their method binding follows how each receives
settings and exchanges data.

Use the numerical method alone when you need neither a working tree nor a context:

```{testcode}
import numpy as np

values = np.array([1.0, 2.0])
scaled = Scale.compute_scaled(values, factor=3.0)
np.testing.assert_array_equal(scaled, [3.0, 6.0])
np.testing.assert_array_equal(values, [1.0, 2.0])
```

Numerical methods take arrays and explicit parameters. They must not
read configuration models or execution contexts, modify inputs, or consult
mutable class state. For computation owned by an analysis, use that analysis's
[configured or numerical methods](analyses.md#reusable-analysis-computations).
Selection and publication steps need no numerical API of their own.

## Compose steps and publish results

`context.data` can be one view or a typed bundle of views, arrays, tables,
and file locations. Publish what later steps need from the invocation. Collect
selected data for persistence or exchange in `context.artifacts`; see
[artifacts and visualization](artifacts.md).
A view gives access to the same products stored in the tree.

The writer below obtains the prior result through `Scale.get_context(data).data`,
exports its dataset, and publishes the file location after the write succeeds:

```{literalinclude} examples/pipeline_example.py
:language: python
:start-at: class WriteSignalConfig
```

If the Scale context or its payload is absent, the writer records `missing_input`
and returns, allowing later steps to run. An available payload can be used even
when its producing context is incomplete. The destination's parent directory
must exist; an existing file is overwritten when writing begins.

```{testcode}
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory() as directory:
    path = Path(directory) / "scaled.nc"
    assert WriteSignal(path=path)(tree) is tree
    publication = WriteSignal.get_context(tree)
    assert publication.completed
    assert publication.data.path == path
    assert tree.attrs[PIPELINE_CONTEXT_KEY][WriteSignal] is publication
    with xr.open_dataset(publication.data.path) as reopened:
        reopened_view = ScaleView(reopened)
        xr.testing.assert_identical(reopened_view.signal, context.data.signal)
        assert PIPELINE_CONTEXT_KEY not in reopened.attrs
```

The tree now holds both contexts. `ScaleContext.data` contains the result view;
`WriteSignalContext.data` contains the published path. The exported file contains
the signal dataset. Reopening it provides data for a new view; it does not
restore the working tree's live contexts or raw input.

With lazy input arrays, `Scale` prepares the calculation without evaluating it.
Its completion means that `run()` returned without recorded failures.
`WriteSignal` evaluates the arrays when writing. A deferred computation error
is recorded on the writer's context and propagates; the Scale context remains
completed. A failed write can leave an incomplete file.

(handle-missing-inputs-and-inspect-failures)=
## Sequential execution and failure handling

### Handle missing inputs and inspect failures

Each step selects its inputs from the available data and prior step contexts.
`run()` returns nothing. A step requiring an unavailable result records the reason
in its context before returning; a step accepting another input can use that input
and complete. Both outcomes allow later steps to run. Completion remains False
while `run()` is executing, even when its failure list is still empty.

Append `StepFailure` instances to `context.failures` as failures occur. Use `kind`
to group records and `details` for JSON-compatible information about each failure.
The list retains every record in append order.

| Kind | Meaning |
| --- | --- |
| `missing_input` | A required input or prior result is unavailable. |
| `invalid_input` | An available input cannot be used by this operation. |
| `exception` | An exception escaped `run()`. |
| `other` | Another failure; describe it with `message` and `details`. |

For a small operation publishing scalar results in its context, a consumer can
use an estimated offset when available:

```{testcode}
class EstimateOffsetContext(StepContext["EstimateOffset", StepConfig]):
    data: float | None = None


class EstimateOffset(Step[StepConfig, EstimateOffsetContext]):
    @classmethod
    def run(cls, data, context):
        if "reference" not in data:
            context.failures.append(
                StepFailure(
                    kind=StepFailureKind.missing_input,
                    message="No reference signal is available.",
                    details={"input": "reference"},
                )
            )
            return
        context.data = float(data["reference"].mean())


class SummarizeContext(StepContext["Summarize", StepConfig]):
    data: float | None = None


class Summarize(Step[StepConfig, SummarizeContext]):
    @classmethod
    def run(cls, data, context):
        signal = data["signal"]
        if EstimateOffset.has_context(data):
            offset = EstimateOffset.get_context(data).data
            if offset is not None:
                signal = signal - offset
        context.data = float(signal.mean())


source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
pipeline = SequentialPipeline(steps=[EstimateOffset(), Summarize()])
assert pipeline(source) is source
assert not EstimateOffset.get_context(source).completed
failures = EstimateOffset.get_context(source).failures
assert len(failures) == 1
failure = failures[0]
assert failure.kind is StepFailureKind.missing_input
assert failure.details == {"input": "reference"}
assert Summarize.get_context(source).completed
assert Summarize.get_context(source).data == 1.5

source["reference"] = xr.DataArray(0.5)
pipeline(source)
assert EstimateOffset.get_context(source).completed
assert EstimateOffset.get_context(source).failures == []
assert Summarize.get_context(source).data == 1.0
```

The consumer decides whether the offset is required. Completing `Summarize`
does not change the outcome recorded by `EstimateOffset`.

Each call starts with a fresh context and an empty failure list. Records from
earlier calls remain on their original contexts. Failure kinds and details are
preserved by model dumps and restoration through `Step.load_context()`.

An `Exception` escaping `run()` appends its message and class name to
`context.failures`, preserving earlier records, before being re-raised. Inspect
that invocation with `Step.get_context(source)` after catching the exception.
`KeyboardInterrupt` and `SystemExit` propagate without being recorded as
operation failures.

### Disable or repeat a step

`SequentialPipeline` skips steps with `config.enabled=False`. Calling a disabled
step directly still runs it. Skipping leaves any earlier context and results in
place; `completed=True` does not prove the step ran in the latest sequence.

Repeating a step with the same alias replaces its previous context, without
clearing results from the data container. Configure distinct aliases to keep
separate invocation records. Aliases do not copy or isolate the working data:

```{testcode}
source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
aliased_tree = xr.DataTree.from_dict({"raw": source})
second = Scale(alias="second", factor=3.0)
pipeline = SequentialPipeline(steps=[Scale(factor=2.0), second])
pipeline(aliased_tree)
assert Scale.get_context(aliased_tree).config.factor == 2.0
assert Scale.get_context(aliased_tree, alias="second").config.factor == 3.0
assert Scale.get_context(aliased_tree).data.signal.values.tolist() == [2.0, 4.0]
second_context = Scale.get_context(aliased_tree, alias="second")
assert second_context.data.signal.values.tolist() == [3.0, 6.0]
assert ScaleView(aliased_tree["scaled"]).signal.values.tolist() == [3.0, 6.0]
assert Scale.has_context(aliased_tree, alias="second")
assert second.context_key == Scale.get_context_key(alias="second")
```

Both calls read `raw` and replace `scaled`. Each published view retains the
dataset selected for its invocation: the first result remains available through
its context, while `scaled` contains the second result. To export both results
as tree leaves, the step would need distinct result locations.

| Lookup | Selected invocation |
| --- | --- |
| `Scale.get_context(aliased_tree)` | Primary (`alias=None`) |
| `Scale.get_context(aliased_tree, alias="second")` | Alias `"second"` |
| `second.get_context(aliased_tree)` | Primary: the lookup is a class method |
| `pipeline.get_contexts(aliased_tree)[second]` | The configured instance's alias |

`has_context()` follows the same explicit-alias rule as `get_context()`.
Use `step.context_key` or `Step.get_context_key(alias=...)` when a string key is
needed.

(recreate-a-step-or-restore-exported-context)=
## Context identity and serialization

### Recreate a step or restore exported context

Use `context.make_step()` to recreate the producer with its saved settings.
Use `Step.dump_context()` to obtain a JSON string. Your writer chooses where to
store it. Read the saved value with `Step.load_context()` on the original
producing class. This example stores the string in a netCDF attribute:

```{testcode}
original = Scale.get_context(aliased_tree)
aliased = Scale.get_context(aliased_tree, alias="second")
product = aliased_tree["scaled"].to_dataset().copy(deep=False)
product.attrs[second.context_key] = Scale.dump_context(aliased)
with TemporaryDirectory() as directory:
    path = Path(directory) / "scaled.nc"
    product.to_netcdf(path)
    with xr.open_dataset(path) as reopened:
        saved = reopened.attrs[second.context_key]
        assert isinstance(saved, str)
        restored = Scale.load_context(saved)
        assert ScaleView(reopened).signal.values.tolist() == [3.0, 6.0]
assert type(original.make_step()) is Scale
assert type(restored.make_step()) is Scale
assert restored.make_step().config.alias == "second"
assert restored.make_step().config.factor == 3.0
assert restored.make_step().context_key == second.context_key
assert aliased.data is not None
assert restored.data is None
```

| Operation | Result |
| --- | --- |
| `context.make_step()` | A new step with the saved configuration and alias; does not execute it. |
| `Scale.load_context(context)` | The live context unchanged. |
| `Scale.dump_context(context)` | JSON for included fields; the producer class is excluded. This example also excludes its live result view. |
| `Scale.load_context(saved)` | A new validated context from JSON or decoded fields; does not attach it to a container. |

Exported fields do not identify the producer. Keep that choice with the exported
record, and restore through the same class. `ScaleContext` excludes its view, so
`load_context()` restores settings and status with `data=None`. It does not
construct a result view. Select the reopened dataset or namespace and construct
its view explicitly. Exclude live payload fields with `Field(exclude=True)` when
defining the context model; included fields must be JSON serializable. The
exporter chooses which contexts to save and which node holds their attributes.
Use the
[analysis workflow](analyses.md#computation-and-producing-configuration) for result
datasets.

Generate a schema for the **exported** fields using Pydantic's serialization mode:

```{testcode}
schema = ScaleContext.model_json_schema(mode="serialization")
assert "step_cls" not in schema["properties"]
assert "data" not in schema["properties"]
assert "config" in schema["required"]
```

The default validation schema cannot describe the live Python class in `step_cls`.
See the {ref}`generated model reference <pipeline-models>`
for configuration fields and failure categories.

### Send a context to another process for diagnostics

Pickle the invocation context when another process needs its settings, status,
and published results for diagnostics. Keep step, context, view, and mapper
classes in importable modules, as in `pipeline_example.py`. Custom payloads must
support pickle, and resources used by those payloads must be available to the
receiving process.

```{testcode}
import pickle

message = pickle.dumps(context)
received = pickle.loads(message)
assert received is not context
assert received.completed == context.completed
assert received.config == context.config
assert received.failures == context.failures
assert received.data.signal.mean().item() == 4.5
```

The receiving process can use `received.data` to compute diagnostics without
running the producing step again. This transports a context; it does not resume
a pipeline. Load pickle data only from trusted sources.

### Context lifetime and storage

- For the default context store, supply a container with an `attrs` mapping, or a
  `meta` mapping if `attrs` is absent. It need not be an xarray object.
- Reserve `__pipeline_context__` for the live Python context objects.
- `Step.get_context()` and the context store return the same attached object.
  Read saved JSON separately with `Step.load_context()`; it returns a detached
  context. Keep serialized values out of the live store.
- Before netCDF/Zarr export, omit that live store from the exported copy. Use
  `Step.dump_context()` for any invocation metadata the product should retain.
- Use `DictContextHandlerMixin` or `MetadataContextHandlerMixin` for typed context
  lookup alone; these mixins do not run steps or track completion.

Read scientific results and producing settings through the
[analysis view](analyses.md#read-results). For invocation records, choose the
transport according to what the receiving process needs:

| Retain | Save | Recover |
| --- | --- | --- |
| Step configuration, status, and included context fields | Write the JSON returned by `Step.dump_context()` | Call the producer's `Step.load_context()` |
| An invocation context and its diagnostic payload | Pickle the context | Unpickle in the diagnostic process with its classes and required resources available |
