# Supporting utilities

Choose the utility for your task; each example below is independent of an
application framework. See the [API reference](modules.rst) for full signatures.

| Task | Module / entry point |
| --- | --- |
| Describe a local or remote location | `tollan.utils.fileloc.fileloc` |
| Open input or create output directories | `tollan.utils.file` |
| Merge nested settings | `tollan.utils.dict.rupdate` |
| Register unique keys for later lookup | `tollan.utils.registry.Registry` |
| Parse dotted command-line overrides | `tollan.utils.cli.dict_from_cli_args` |
| Read or write YAML | `tollan.utils.yaml` |
| Convert units or select table rows | `tollan.utils.np`, `tollan.utils.table` |
| Query pandas tables with membership and bitmask predicates | `tollan.utils.pandas` |
| Summarize labeled arrays with median and scatter | `tollan.utils.xarray.reduce_median_mad` |
| Arrange plots | `tollan.plot.plotly`, `tollan.plot.mpl` |
| Log operations or format display values | `tollan.utils.log`, `tollan.utils.fmt` |

## Describe file locations without opening them

`fileloc()` validates local paths, remote host/path pairs, and URLs. It does not
open files, download data, or check whether a remote resource exists.

```{testcode}
from tollan.utils.fileloc import fileloc

source = fileloc(("archive", "sample.nc"), remote_parent_path="/data")
assert source.as_rsync_arg() == "archive:/data/sample.nc"
assert source.path.as_posix() == "/data/sample.nc"
```

A remote `path` is a decoded path on that host, not a local copy. Use
`FileLocField` in Pydantic models when local paths should inherit the
[validation root](validation-types.md#paths-and-file-locations).

| I/O task | Helper | Effect |
| --- | --- | --- |
| Read a path, URL, or stream | `ensure_readable_fileobj()` | Context manager; leaves caller-owned streams open. |
| Prepare a file's parent directory | `ensure_path_parent_exists()` | Creates missing directories. |
| Prepare an output directory | `get_or_create_dir()` | Creates the directory if needed. |

## Merge settings and parse dotted overrides

`rupdate()` updates its first argument recursively. List-index and slice keys
apply patches to an existing list; the empty bracket key appends values.

```{testcode}
from tollan.utils.cli import dict_from_cli_args
from tollan.utils.dict import rupdate

settings = {"reader": {"format": "csv"}, "items": ["base"]}
rupdate(settings, {"reader": {"header": True}, "items": {"[]": ["extra"]}})
assert settings == {"reader": {"format": "csv", "header": True}, "items": ["base", "extra"]}
overrides = dict_from_cli_args(["--reader.header", "false"])
assert overrides == {"reader": {"header": False}}
```

CLI override values use YAML parsing. For application configuration, prefer
`RuntimeContext` and its documented precedence rules instead of composing a
second loading workflow from these lower-level helpers.

## Register entries for lookup

Use {class}`~tollan.utils.registry.Registry` when each key must identify one
registered value. It starts empty and supports normal mapping lookups and
iteration in registration order.

```{testcode}
from tollan.utils.registry import Registry

readers = Registry[str, type]()
readers.register("text", str)
assert readers["text"] is str
assert list(readers) == ["text"]

try:
    readers.register("text", str)
except ValueError:
    pass
else:
    raise AssertionError("An existing key must not be registered again")
assert readers["text"] is str
```

Registering an existing key raises `ValueError`, even for the same value, and
leaves the existing entry unchanged. Item assignment, deletion, and `update()`
are not supported. Validate entries before registering them; values are stored
as supplied. Use `dict(readers)` when you need an independent mapping snapshot.

## Read and write YAML

| Input / output | Call |
| --- | --- |
| Parse YAML text | `yaml_loads(text)` |
| Read a file | `yaml_load(Path(...))` |
| Produce YAML text | `yaml_dump(value)` |
| Write a file or stream | `yaml_dump(value, output=...)` |

`yaml_load()` also accepts strings: an existing filename is read as a file;
otherwise the string is parsed as YAML text.

```{testcode}
from tollan.utils.yaml import yaml_dump, yaml_loads

text = yaml_dump({"threshold": 3, "enabled": True})
assert yaml_loads(text) == {"threshold": 3, "enabled": True}
```

The dumper emits plain YAML for scalar quantities, times, paths, and enum values.
Loading those values does not reconstruct their original Python types; use a
validated model when you need that conversion. See
`FrozenBaseModel.model_validate_yaml()` and `model_dump_yaml()`.

## Work with units and table rows

`tollan.utils.np` provides `strip_unit()`, `attach_unit()`, and `ensure_unit()`
for NumPy arrays and Astropy quantities. These functions make unit removal and
conversion explicit. For labeled xarray data, use the
[units accessor](data-adapters.md#work-with-xarray-units).

`tollan.utils.table.TableValidator` checks table requirements and evaluates row
queries. Use [xarray table projection](data-adapters.md#project-columnar-xarray-data-into-a-qtable)
when your source is a columnar Dataset and you need an Astropy QTable.

## Query pandas tables

Use {func}`~tollan.utils.pandas.query` on any DataFrame, without creating a model
table accessor. It accepts the same expressions as
[model-table queries](model-tables.md#query-the-collected-values), including
`contains`, `bits_any_set`, and `bits_all_set`. Only use trusted expressions.
Supply additional constants or functions through `namespace`; column names
take precedence.

```{testcode}
import pandas as pd
from tollan.utils.pandas import contains, query

table = pd.DataFrame({
    "tags": [["science", "reviewed"], ["engineering"], [], None],
    "exposure": [60, 30, 10, 0],
})
selected = query(table, 'contains(tags, "science") and exposure > limit',
                 namespace={"limit": 30})
assert selected.index.tolist() == [0]

# The predicates also return masks for ordinary pandas selection.
mask = contains(table["tags"], "science")
assert table.loc[mask].index.tolist() == [0]
```

## Reduce labeled arrays to median and scatter

Use {func}`~tollan.utils.xarray.reduce_median_mad` to summarize real-valued samples
along one dimension. It returns two Datasets:

| Output | Meaning |
| --- | --- |
| `median` | Median of each variable carrying `dim`. |
| `mad_std` | Median absolute deviation from the median, multiplied by 1.4826; scatter among samples, not uncertainty in the median. |

Dataset and variable attributes, including units, are retained, along with the
participating variables' coordinates that do not depend on `dim`. NaNs propagate
in each reduced slice. An unnamed DataArray becomes a variable named `data`.

```{testcode}
import dask
import xarray as xr
from astropy import units as u
from tollan.utils.xarray import reduce_median_mad

values = xr.DataArray(
    [1.0, 2.0, 8.0], dims="sample", name="signal",
).u.set(u.V).chunk(sample=1)
median, scatter = reduce_median_mad(values, dim="sample")
median, scatter = dask.compute(median, scatter)
assert median.signal.item() == 2.0
assert scatter.signal.item() == 1.4826
assert scatter.signal.u.unit == u.V
```

1. Select the samples to combine, and normalize first if their scales should differ.
2. Call the reduction. It checks dimension membership immediately and raises
   `ValueError` if no variable carries `dim` or that dimension is empty;
   numerical work remains lazy even
   for NumPy input.
3. Compute both outputs together to share work. Keep source files available
   until the results have been loaded. Xarray can reopen path-based sources;
   their original handles need not stay open.

Each variable follows NumPy's median dtype rules: integer inputs yield float64,
while float32 and float64 retain their precision. The lazy dtype matches the
computed result.

Each task needs the full reduction dimension in memory. Select samples and chunk
the other dimensions to control memory use.

## Build a Plotly figure

```{testcode}
import plotly.graph_objects as go
from tollan.plot.plotly import make_subplots, update_subplot_layout

figure = make_subplots(1, 2)
figure.add_trace(go.Scatter(x=[0, 1], y=[2, 3]), row=1, col=1)
update_subplot_layout(figure, {"yaxis": {"title": "Signal"}}, row=1, col=1)
assert figure.layout.yaxis.title.text == "Signal"
```

- Rows and columns are one-based.
- `update_subplot_layout()` modifies the figure; `make_subplot_layout()` returns
  an adapted layout dictionary.
- `show_in_dash()` starts a local server and waits for user input to stop it.
- For Matplotlib, `move_axes()` transfers an axes and its artists into a destination
  placeholder and optionally closes the original figure.

## Logging and formatting

Use `tollan.utils.log.logger` for logging, and `timeit` or `logit` to report
operation timing or entry/exit. `reset_logger()` replaces all active handlers;
configure it at the application boundary. Tollan's CLI already provides logging
options, described in [command-line applications](cli.md).

Formatting helpers return strings for display. `pformat_mask()` expects a
nonempty boolean mask; `pformat_bitmask()` summarizes the named flags in an
integer mask. Neither changes the input data.

```{toctree}
:maxdepth: 1

generic-runtime-bindings
```
