# Run a sequence of configured steps

Run configured computations in order and inspect each step's results on the
data container.

| Need | Use |
| --- | --- |
| Validate a step's settings | A `StepConfig` subclass |
| Store completion status and outputs | A `StepContext` subclass |
| Run one computation | A `Step` subclass implementing `run()` |
| Run enabled steps in order | `SequentialPipeline` |
| Export result datasets with their producing configuration | [xarray analyses](data-adapters.md#store-analysis-results-in-a-datatree) |

## Define and run a step

1. Declare settings on a `StepConfig` subclass.
2. Declare outputs on a `StepContext` subclass.
3. Bind both to a `Step` and implement `run(data, context)`.
4. Call the step or add it to a `SequentialPipeline`.

```{graphviz}
digraph step {
    rankdir=LR;
    node [shape=box];
    StepConfig -> Step [label="settings"];
    Step -> StepContext [label="creates per call"];
    Step -> "data container" [label="run()"];
    "data container" -> StepContext [label="get_context()"];
}
```

```{testcode}
import xarray as xr
from tollan.pipeline import SequentialPipeline, Step, StepConfig, StepContext


class ScaleConfig(StepConfig):
    factor: float = 2.0


class ScaleContext(StepContext["Scale", ScaleConfig]):
    data: float | None = None


class Scale(Step[ScaleConfig, ScaleContext]):
    @classmethod
    def run(cls, data, context):
        data["signal"] = data["signal"] * context.config.factor
        context.data = float(data["signal"].mean())
        return True


source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
pipeline = SequentialPipeline(steps=[Scale(factor=3.0)])
assert pipeline(source) is source
context = Scale.get_context(source)
assert context.completed
assert context.data == 4.5
assert context.config.factor == 3.0
```

Construct a step with a configuration model, keyword settings, or both.
Keywords override a supplied model's values and are validated again. The step
and context must bind the same configuration type.

| Operation | Result |
| --- | --- |
| `step(source)` | Runs the step; replaces its previous context. |
| `step(source, return_context=True)` | Returns `(source, context)`. |
| `run()` returns `True` | Marks the context complete; the pipeline continues. |
| `run()` returns `False` | Leaves the context incomplete; the pipeline continues. |
| `run()` raises | Propagates the exception and stops the pipeline; prior mutations remain. |
| `Step.get_context(source)` before execution | Raises `KeyError`. |

Context lookup, including `has_context()`, attaches an empty context store when
the container has none.

## Disable or repeat a step

`SequentialPipeline` skips steps with `config.enabled=False`. Calling a disabled
step directly still runs it. Distinct instances of the same step class share one
context key, so the later execution replaces the earlier context. Use `alias()`
to give repeated steps distinct keys:

```{testcode}
SecondScale = Scale.alias("second")
source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
pipeline = SequentialPipeline(steps=[Scale(factor=2.0), SecondScale(factor=3.0)])
pipeline(source)
assert Scale.get_context(source).data == 3.0
assert SecondScale.get_context(source).data == 9.0
```

```{warning}
Creating an alias can currently change which step `context.make_step()`
reconstructs for an existing context. Construct the intended step class
explicitly when reusing its configuration.
```

## Context lifetime and storage

- Supply a container with an `attrs` mapping, or a `meta` mapping if `attrs` is absent.
- Reserve `__pipeline_context__` for the live Python context objects.
- Remove that entry before netCDF/Zarr export, or use the analysis workflow to
  persist result datasets and configuration.
- Use `DictContextHandlerMixin` or `MetadataContextHandlerMixin` for typed context
  lookup alone; these mixins do not run steps or track completion.
