# Backend adapters

Use a mapper to read fields by the names in your schema. Tollan provides
`XarrayMapper` for labeled arrays, `NetCDF4Mapper` for open NetCDF files, and
`DataFrameMapper` for pandas tables. See
[schemas and mappings](schema-mapping-accessors.md) for alternative field names,
conditional mappings, and defaults.

## Read an xarray Dataset

Declare variables with `NameMapping.var()`, attributes with
`NameMapping.attr()`, and dimension lengths with `NameMapping.dim()`:

```{testcode}
from dataclasses import dataclass

import xarray as xr
from tollan.accessor import Mapping, NameMapping, Schema
from tollan.accessor.xarray import XarrayMapper


@dataclass
class ReadingsSchema(Schema):
    temperature: Mapping = NameMapping.var(("temp", "temperature"))
    sample: Mapping = NameMapping.var("sample")
    n_samples: Mapping = NameMapping.dim("sample")
    label: Mapping = NameMapping.attr("label")


class ReadingsMapper(XarrayMapper[ReadingsSchema]):
    pass


ds = xr.Dataset(
    {"temp": ("sample", [20.0, 21.0, 22.0])},
    coords={"sample": [10, 20, 30]},
    attrs={"label": "Room A"},
)
mapper = ReadingsMapper.from_data_source(ds)

temperature = mapper.get_arr(ds, mapper.schema.temperature)
assert temperature.dims == ("sample",)
assert mapper.get_dim(ds, mapper.schema.n_samples) == 3
assert mapper.get_str(ds, mapper.schema.label) == "Room A"
assert mapper.get_arr(ds, mapper.schema.sample).to_numpy().tolist() == [10, 20, 30]
```

The `sample` coordinate contains the values `[10, 20, 30]`; its dimension
length is `3`. Use separate schema fields when you need both.

## Choose a read method

The following methods are shared by the xarray, netCDF4, and pandas mappers.
Each takes a source and a schema field, for example
`mapper.get_var(ds, mapper.schema.temperature)`.

| Method | Result | Does it load variable values? |
| --- | --- | --- |
| `get_var()` | Native variable: xarray DataArray, netCDF4 Variable, or pandas Series | No; retains its backend, labels, and metadata |
| `get_value()` | Variable values, an attribute value, or a dimension length from the supplied source | Yes for variables; may trigger disk reads or Dask computation |
| `get_value_or_default()` | Source value, or the configured fallback if the mapped field is absent | Yes for an existing variable; no variable read for a fallback |
| `get_scalar()` | Scalar variable value, unchanged attribute value, or dimension length | Only the requested variable, after checking its shape |
| `get_str()` | One decoded string, with outer whitespace and null padding removed | Only the requested variable, after checking its shape and dtype |
| `get_dim()` | Current integer dimension length | No |
| `has_var()`, `has_attr()`, `has_dim()` | Whether the field exists at its mapped location in this source | No |

Xarray and pandas also provide aliases for `get_var()` and `has_var()`:

| Mapper | Getter alias | Existence-check alias |
| --- | --- | --- |
| `XarrayMapper` | `get_arr()` | `has_arr()` |
| `DataFrameMapper` | `get_col()` | `has_col()` |

The aliases have identical return types, loading behavior, and errors. NetCDF
uses the shared `get_var()` and `has_var()` methods directly. These shared names
are available on all three backends.

Metadata access may involve backend I/O, but `get_var()`, `get_dim()`, and the
existence checks do not request array values. `get_value()` returns NumPy values
for variables, preserving netCDF4 masking and scaling. Dask-backed DataArrays
returned by `get_arr()` remain lazy.

For xarray and netCDF4, `get_scalar()` accepts zero-dimensional variables and
single-element string variables; bytes remain bytes. `get_str()` also accepts
one-dimensional S1/U1 character arrays. It decodes bytes using UTF-8 by default;
pass `encoding="latin-1"`, for example, for another encoding. Object-typed values
must be read to verify that they contain text.

For pandas, use `get_scalar()` and `get_str()` for attributes, not columns.
Columns remain Series even when the frame has only one row; these methods do
not select a row implicitly. DataFrame mappers do not support dimensions.

Only `get_value_or_default()` uses configured fallbacks. All other getters read
the supplied source. None substitutes values captured with `resolve_value=True`
for a source read.

Xarray also provides `get_shape()` to inspect a variable's shape without
loading values. For trees, `get_node()` returns the native subtree and
`has_node()` checks its presence. `get_value()` on a node mapping also returns
the subtree without loading its arrays; node mappings are not scalar fields.

For optional fields, check their availability before reading:

```{testcode}
if mapper.schema.label in mapper:
    label = mapper.get_str(ds, mapper.schema.label)
```

Membership checks the source used to create the mapper. You can reuse a mapper
with another source having the same field names and locations; `has_var()`,
`has_attr()`, and `has_dim()` check the source passed to that call. Create a new
mapper when you need to select different names or locations.

## Supply a fallback for an optional field

Pass defaults when creating the mapper, then use `get_value_or_default()`:

```{testcode}
label_field = ReadingsMapper.schema.label
mapper_with_defaults = ReadingsMapper.from_data_source(
    ds, defaults={label_field: "Unknown"}
)
assert mapper_with_defaults.get_value_or_default(ds, label_field) == "Room A"
assert mapper_with_defaults.get_value_or_default(xr.Dataset(), label_field) == "Unknown"
```

The mapper retains the fallback even when the original source has the field.
Every call reads the supplied source at the recorded name and location; the
fallback is used only if that field is absent. Present values such as `None`,
zero, and empty strings are returned unchanged. Read errors propagate rather
than triggering the fallback. If neither a source field nor a fallback is
available, `get_value_or_default()` raises `KeyError`.

Pass `None` as the source to use only the configured fallback. Fallbacks are
returned as supplied, without string decoding or scalar validation.
`get_str()`, `get_scalar()`, and the other source-only getters never use them.

A bare name that was absent during resolution has `location=None`; it cannot
be read until you create a new mapper against a source containing that field.
`get_value_or_default()` can still return its fallback. Use an explicit location,
such as `NameMapping.attr("label")`, when the field may appear in a later source
and you want to reuse the same mapper.

## Add convenient xarray properties

Use `XarrayAccessorBase` to expose the reads your application uses frequently:

```{testcode}
from tollan.accessor.xarray import XarrayAccessorBase


@xr.register_dataset_accessor("readings")
@xr.register_datatree_accessor("readings")
class ReadingsAccessor(XarrayAccessorBase[ReadingsMapper]):
    @property
    def temperature(self) -> xr.DataArray:
        return self.mapper.get_arr(self.data_source, self.mapper.schema.temperature)


assert ds.readings.temperature.identical(temperature)

tree = xr.DataTree(dataset=ds)
assert tree.readings.temperature.identical(temperature)
```

An accessor accepts a Dataset, DataArray, or DataTree. With a DataTree, it reads
the current node. To read a child, use the accessor on that child:

```{testcode}
tree["processed"] = xr.DataTree(dataset=ds)
assert tree["processed"].readings.temperature.identical(temperature)
```

Direct mapper calls also accept a DataTree. A mapping's `parent` selects the
containing subtree; without a parent, fields belong to the supplied node.
`parent / NameMapping.var("signal")` is shorthand for
`NameMapping.var("signal", parent=parent)`. Attributes, dimensions, and child
paths support the same parent declaration. Variable mappings also accept direct
slash paths to variables or coordinates. Use
`mapper.get_node(tree, schema.result)` to retrieve a subtree without loading arrays.
See [subtree paths](schema-mapping-accessors.md#subtree-paths) for a complete example.
A DataArray exposes its own attributes, coordinates, and named array; an unnamed
array uses the name `"data"`.

Use `ensure_dataset()` or `ensure_datatree()` when an operation requires one of
those containers. `ensure_dataset()` preserves a Dataset, selects the current
Dataset of a DataTree node, or wraps a DataArray under its existing variable name
(default `data` when unnamed). Array attributes stay on the variable. A private
marker identifies DataArray wrappers for recovery by `unwrap_data_source()`.

`ensure_datatree()` returns an existing tree unchanged or places the converted
Dataset at an unnamed root. Accessors accept the resulting containers directly.
To recover a wrapped DataArray with its variable attributes, use
`unwrap_data_source()`:

```{testcode}
from tollan.accessor.xarray import ensure_datatree, unwrap_data_source

container = ensure_datatree(ds["temp"])
source = unwrap_data_source(container)
array_mapper = ReadingsMapper.from_data_source(source)
assert array_mapper.get_arr(source, array_mapper.schema.temperature).identical(
    ds["temp"]
)
```

## Work with xarray units

Importing `tollan.accessor.xarray` enables the DataArray `u` accessor:

```{testcode}
from astropy import units as u

length = xr.DataArray([1.0, 2.0], dims="sample").u.set(u.m)
length_cm = length.u.to(u.cm)
assert length_cm.to_numpy().tolist() == [100.0, 200.0]
assert length.u.unit == u.m
```

Units are stored in `attrs["units"]`. `.u.set()` and `.u.unset()` return
shallow copies by default; use `inplace=True` to change the original object's
attributes. `.u.to()` converts values and preserves lazy computation, labels,
and unrelated attributes. It clears the converted variable's storage encoding.

`.u.quantity` presents floating-point and complex NumPy data as an Astropy
Quantity view sharing the source's storage. Treat it as read-only. Representation
changes, such as promoting integers to floating point, may require a copy.
For Dask data, it returns a lazy array that computes to a Quantity. If no unit is
set, it returns the DataArray itself.

## Read a NetCDF file

Bind a schema to `NetCDF4Mapper`, then pass an open Dataset to its read methods.
This example creates a small temporary file with the fields used above:

```{testcode}
from pathlib import Path
from tempfile import TemporaryDirectory

import netCDF4 as nc
from tollan.accessor.netcdf4 import NetCDF4Mapper


class FileReadingsMapper(NetCDF4Mapper[ReadingsSchema]):
    pass


with TemporaryDirectory() as directory:
    path = Path(directory) / "readings.nc"
    with nc.Dataset(path, "w") as dataset:
        dataset.createDimension("sample", 3)
        dataset.createVariable("temp", "f8", ("sample",))[:] = [20.0, 21.0, 22.0]
        dataset.createVariable("sample", "i4", ("sample",))[:] = [10, 20, 30]
        dataset.setncattr("label", "Room A")

    with nc.Dataset(path) as dataset:
        file_mapper = FileReadingsMapper.from_data_source(dataset)
        variable = file_mapper.get_var(dataset, file_mapper.schema.temperature)
        assert variable is dataset.variables["temp"]
        values = file_mapper.get_value(dataset, file_mapper.schema.temperature)
        assert values.tolist() == [20.0, 21.0, 22.0]
        assert file_mapper.get_dim(dataset, file_mapper.schema.n_samples) == 3
        assert file_mapper.get_str(dataset, file_mapper.schema.label) == "Room A"
```

Keep the Dataset open until the reads are finished. Variable reads preserve
netCDF4's automatic masking and scale/offset decoding. Attributes are returned
unchanged, and dimension reads return their current integer length.

## Project columnar xarray data into a QTable

`dataset_to_qtable()` exposes one row dimension as an Astropy QTable. Numeric
columns with a `units` attribute become Quantity columns; plain columns retain
their dtypes. The Dataset remains the storage representation for netCDF/Zarr.

```{testcode}
from tollan.accessor.xarray import dataset_to_qtable, select_table_rows

readings = xr.Dataset(
    {
        "batch": ("row", [0, 0, 1]),
        "distance": ("row", [1.0, 2.0, 3.0], {"units": "km"}),
    },
    attrs={"label": "Survey"},
)
selected = select_table_rows(readings, readings["batch"] == 0, dim="row")
table = dataset_to_qtable(selected, dim="row")
assert table["distance"].to_value("m").tolist() == [1000.0, 2000.0]
assert table.meta["label"] == "Survey"
```

Selection computes only the boolean mask; payload arrays remain lazy. It uses
positions, preserving source row order without aligning mask coordinate labels.
Projection materializes the selected columns, so keep the input open until it finishes. By default, table
columns share buffers where possible; use `copy=True` for independently editable
columns. Editing a table does not persist changes to its source file.

All data variables are included by default. Use
`columns={"length": "distance"}` to select and rename columns in output order;
coordinates must be requested explicitly. Every selected column must have
exactly the specified row dimension. The utility does not flatten or broadcast
multidimensional data. A DataTree input selects the current node's dataset.

## Read a pandas DataFrame

Use `.var()` for columns and `.attr()` for values in `DataFrame.attrs`:

```{testcode}
import pandas as pd
from tollan.accessor.pandas import DataFrameMapper


@dataclass
class TableReadingsSchema(Schema):
    temperature: Mapping = NameMapping.var(("temp", "temperature"))
    label: Mapping = NameMapping.attr("label")


class TableReadingsMapper(DataFrameMapper[TableReadingsSchema]):
    pass


frame = pd.DataFrame({"temp": [20.0, 21.0, 22.0]})
frame.attrs["label"] = "Room A"
table_mapper = TableReadingsMapper.from_data_source(frame)
column = table_mapper.get_col(frame, table_mapper.schema.temperature)
assert column.equals(frame["temp"])
assert table_mapper.get_value(frame, table_mapper.schema.temperature).tolist() == [
    20.0,
    21.0,
    22.0,
]
assert table_mapper.get_str(frame, table_mapper.schema.label) == "Room A"
```

`get_col()` retains the column's index and dtype. `get_value()` returns NumPy
values without the pandas index. Attribute values are returned unchanged by
`get_value()` and `get_scalar()`.

## API reference

- {class}`tollan.accessor.xarray.XarrayMapper`
- {class}`tollan.accessor.xarray.XarrayAccessorBase`
- {class}`tollan.accessor.xarray.UnitsAccessor`
- {func}`tollan.accessor.xarray.dataset_to_qtable`
- {func}`tollan.accessor.xarray.select_table_rows`
- {class}`tollan.accessor.netcdf4.NetCDF4Mapper`
- {class}`tollan.accessor.pandas.DataFrameMapper`
