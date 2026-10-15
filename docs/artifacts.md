# Artifacts and visualization

Use artifacts to collect the part of an operation's data that you want to persist
or exchange. You can select a subset or the whole data context. Each entry keeps
data in its native representation with the specification that can write it.

Visualization is one way to consume data. A figure is also data: use it directly
in Dash or a notebook, or retain it as an artifact for later export.

| Task | API |
| --- | --- |
| Select or assemble artifact data | A concrete `ArtifactSpec[T]` |
| Retain selected data with its effective spec | `ArtifactContext.add(spec, data)` |
| Retrieve a typed artifact | `artifacts[SpecClass]` or `artifacts[configured_spec]` |
| Write a retained artifact | `artifact.spec.write(artifact.data, path=destination)` |
| Define a configurable visualization | Subclass `VizBase[T]`, or `PlotlyViz` for a Plotly figure |
| Construct a figure | The concrete visualization's typed `__call__` |
| Export an existing Plotly figure | `PlotlyFigExport()(path, figure)` |
| Display named figures locally | `PlotlyFigShowInDash()({"label": figure})` |
| Embed a figure in Dash | `dcc.Graph(figure=figure)` |

## Select data for persistence or exchange

Subclass `ArtifactSpec[T]` for the data representation you need. Define the inputs
to `__call__` and implement `write` for the prepared data. This example selects
two counts from an operation's data and writes them as JSON:

```{testcode}
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tollan.pipeline import ArtifactContext, ArtifactFile, ArtifactSpec


class RecordSpec(ArtifactSpec[dict[str, int]]):
    fields: tuple[str, ...]

    def __call__(self, data: dict[str, int]) -> dict[str, int]:
        return {name: data[name] for name in self.fields}

    def write(self, data: dict[str, int], *, path: Path) -> list[ArtifactFile]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return [ArtifactFile(path=path, format="json")]


operation_data = {"accepted": 12, "rejected": 2, "examined": 20}
record_spec = RecordSpec(fields=("accepted", "rejected"))
selected_data = record_spec(operation_data)
selected_artifacts = ArtifactContext()
selected_entry = selected_artifacts.add(record_spec, selected_data)
assert selected_entry.data == {"accepted": 12, "rejected": 2}
assert selected_entry.data is selected_data

with TemporaryDirectory() as directory:
    destination = Path(directory) / "counts.json"
    selected_entry.spec.write(selected_entry.data, path=destination)
    assert json.loads(destination.read_text()) == selected_data
```

The selected data is an ordinary dictionary before export. Adding it to the
context retains it by reference; the other operation data is not added. A
consumer can read `selected_entry.data` without writing a file or creating a figure.

## Define and use a visualization

Subclass `PlotlyViz` to declare figure settings and a typed input signature.
This example accepts a one-dimensional NumPy array. Its configured call uses
`line_width`; the classmethod also lets callers supply that setting directly.

```{literalinclude} examples/artifact_example.py
:language: python
:start-at: class SignalViz
:end-before: class HistogramViz
```

Save the {download}`complete example <examples/artifact_example.py>` as
`artifact_example.py` on your Python import path. Construct a figure and use it
directly:

```{testcode}
import numpy as np
from dash import dcc
from artifact_example import SignalViz

values = np.array([1.0, 3.0, 2.0])
viz = SignalViz(line_width=3.0, save_formats=["html", "json"])
figure = viz(values)
graph = dcc.Graph(figure=figure)
assert figure.data[0].line.width == 3.0

direct = SignalViz.make_figure(values, line_width=1.0)
assert direct.data[0].line.width == 1.0
```

Concrete visualizations determine their input types and loading behavior. Figure
construction returns the native object; writing and local display are separate
calls. A backend other than Plotly can subclass `VizBase[T]` and implement
`write` and `show` for its presentation type.

## Export and display existing figures

`viz.write` accepts a filename stem and appends each configured format. The
standalone exporter accepts an exact filename. Both create parent directories
and overwrite existing files.

```{testcode}
from pathlib import Path
from tempfile import TemporaryDirectory
from tollan.plot.plotly import PlotlyFigExport

with TemporaryDirectory() as directory:
    root = Path(directory)
    files = viz.write(figure, path=root / "signal.v1")
    assert [item.path.name for item in files] == ["signal.v1.html", "signal.v1.json"]
    receipt = PlotlyFigExport()(root / "standalone.html", figure)
    assert receipt.path.is_file()
```

| Setting | Effect |
| --- | --- |
| `save=False` | `viz.write` returns an empty list and writes nothing |
| `save_formats` | Selects HTML, JSON, PNG, JPG/JPEG, WebP, PDF, or SVG |
| `save_plotly.html` | Controls embedded Plotly.js, full document versus fragment, browser opening, and animation playback |
| `save_plotly.image` | Controls image width, height, and resolution scale |
| `show_plotly.host`, `show_plotly.port` | Configures local display; port `0` selects a free port |

HTML defaults to a self-contained document with animation playback disabled.
JSON stores the figure specification and can be read with `plotly.io.read_json`.
It does not include a browser runtime or Dash callbacks. See Plotly's
[HTML export guide](https://plotly.com/python/interactive-html-export/) and
[JSON writer reference](https://plotly.com/python-api-reference/generated/plotly.io.write_json.html).
Static images require [Kaleido and Chrome](https://plotly.com/python/static-image-export/);
install Kaleido in the rendering environment to use those formats.

For local viewing, call `viz.show(figure)` or display several named figures:

```python
from tollan.plot.plotly import PlotlyFigShowInDash

display = PlotlyFigShowInDash(port=8050)
display({"Signal": figure, "Detail": direct}, title="Diagnostics")
```

The call runs until you confirm the terminal's stop prompt. Interruption also
closes the server. For an existing Dash application, pass figures to your own
`dcc.Graph` components, or embed the display helper's tabbed layout:

```{testcode}
import dash_mantine_components as dmc
from dash import Dash
from tollan.plot.plotly import PlotlyFigShowInDash

app = Dash("artifact_example")
display = PlotlyFigShowInDash()
app.layout = dmc.MantineProvider(
    display.make_layout({"Signal": figure, "Detail": direct}, title="Diagnostics")
)
```

`make_layout` constructs components without starting a server. Your application
owns its callbacks and server lifetime.

## Artifact retention and composition

### Retain artifacts for later use

`ArtifactContext` stores objects and their effective specs by reference. Lookup
by class selects its primary artifact; lookup by instance also uses that
instance's alias. Adding the same class and alias replaces its entry.

```{testcode}
from tollan.pipeline import ArtifactContext

artifacts = ArtifactContext()
entry = artifacts.add(viz, figure)
assert artifacts[SignalViz] is entry
assert entry.data is figure
assert entry.spec is viz

detail = SignalViz(alias="detail", line_width=1.0)
artifacts.add(detail, detail(values))
assert artifacts[detail].spec is detail
assert len(artifacts) == 2
assert artifacts.get(SignalViz) is entry
```

Iteration yields qualified spec keys, optionally suffixed with aliases.
`artifacts.values()` yields entries. The context provides storage and lookup;
use the retained spec to materialize an entry:

```{testcode}
with TemporaryDirectory() as directory:
    entry = artifacts[SignalViz]
    files = entry.spec.write(entry.data, path=Path(directory) / "selected")
    assert all(item.path.exists() for item in files)
```

`ArtifactFile` receipts contain the written path and representation format.
Writers return them after successful writes. Errors propagate, and files from
earlier successful writes may remain. A product publisher supplies staging
destinations, records installed files, and commits the completed product.

### Configure a set of artifacts

An `ArtifactSpec[ArtifactContext]` can declare named child specs. Its typed call
constructs the artifacts; its writer assigns relative names beneath the supplied
directory. The example below applies a shared format list and exporter to both
figures while preserving each figure's construction settings and `save` flag.

```{literalinclude} examples/artifact_example.py
:language: python
:start-at: class HistogramViz
:end-before: class SignalPlotConfig
```

The produced entries retain those effective specs. Exporting them later uses the
same settings even when the caller has only the entries. Configuration fields
remain ordinary Pydantic fields; use a concrete spec class or instance for lookup.

```{testcode}
from artifact_example import SignalArtifacts

spec = SignalArtifacts(save_formats=["json"], signal=SignalViz(line_width=4.0))
produced = spec(values)
with TemporaryDirectory() as directory:
    files = spec.write(produced, path=Path(directory))
    assert {item.path.name for item in files} == {"signal.json", "histogram.json"}
```

## Use artifacts in a step

Declare the concrete spec type on the step config's `artifacts` field. The
example plot step creates figures in `run`, keeps them in `context.artifacts`,
and optionally writes or displays them. `save_path=None` leaves export deferred;
`show=False` leaves local display disabled.

```{literalinclude} examples/artifact_example.py
:language: python
:start-at: class SignalPlotConfig
```

Invoke it like any other [pipeline step](pipelines.md):

```{testcode}
import xarray as xr
from artifact_example import SignalPlot

source = xr.Dataset({"signal": ("sample", values)})
SignalPlot(artifacts=spec)(source)
context = SignalPlot.get_context(source)
assert context.completed
assert context.artifacts[SignalViz].data.data[0].line.width == 4.0
assert list(source.data_vars) == ["signal"]

with TemporaryDirectory() as directory:
    deferred = context.config.artifacts.write(context.artifacts, path=Path(directory))
    assert len(deferred) == 2
```

Each invocation receives a fresh artifact context. `context.data` is the step's
typed payload; `context.artifacts` collects selected data with specifications for
persistence or exchange. This example retains figures there. Step `__call__`
still records completion and failures, and the classmethod `run` uses
configuration supplied through its context.

### Save configuration and transport live artifacts

JSON step records retain the concrete artifact configuration and step status.
They omit the live artifact context. Restoring such a record starts with an empty
artifact context:

```{testcode}
record = SignalPlot.dump_context(context)
restored = SignalPlot.load_context(record)
assert restored.config == context.config
assert restored.completed
assert not restored.artifacts
```

Pickle retains the live objects and effective specs when those objects support
pickling. The receiving process needs their defining classes and any required
source resources; see [pipeline context transport](pipelines.md#send-a-context-to-another-process-for-diagnostics).

```{testcode}
import pickle
import json

transported = pickle.loads(pickle.dumps(context))
assert json.loads(transported.artifacts[SignalViz].data.to_json()) == json.loads(
    context.artifacts[SignalViz].data.to_json()
)
```

## API reference

See {ref}`artifact-visualization-models`,
{class}`tollan.pipeline.ArtifactContext`, {class}`tollan.pipeline.Artifact`, and
{class}`tollan.pipeline.ArtifactFile`.
