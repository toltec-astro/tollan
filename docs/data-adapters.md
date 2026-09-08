# Data adapters

Tollan supplies storage-specific mappers for xarray, netCDF4, and pandas. They
all use the [schema and mapper model](schema-mapping-accessors.md): resolve a
schema once to obtain a concrete field plan, then pass a compatible source to
each read operation.

Only the xarray integration provides a specialized accessor base. The netCDF4
and pandas integrations are mapper implementations that can be used directly
or placed behind a domain accessor built from `AccessorBase`.

## Choosing an adapter

| Source | Tollan class | Labeled read | Raw read |
| --- | --- | --- | --- |
| `xarray.Dataset`, `DataArray`, or `DataTree` | `XarrayMapper`, `XarrayAccessorBase` | `get_arr()` returns a `DataArray` | `get_value()` returns an attribute value or NumPy array |
| `netCDF4.Dataset` | `NetCDF4Mapper` | — | `get_value()` returns an array representation of a variable or attribute |
| `pandas.DataFrame` | `DataFrameMapper` | — | `get_value()` returns a NumPy column array or raw `DataFrame.attrs` value |

The schema declaration is independent of the backend:

```python
from dataclasses import dataclass

from tollan.accessor import Mapping, NameMapping, Schema


@dataclass
class ObservationSchema(Schema):
    signal: Mapping = NameMapping(("signal", "data"))
    observation_id: Mapping = NameMapping(("observation_id", "obsid"))
```

## Xarray

`XarrayMapper` understands xarray variables, coordinates, and attributes.
`XarrayAccessorBase` adds automatic mapper construction and presents a uniform
Dataset through its `data_source` property.

```python
import xarray as xr

from tollan.accessor.xarray import XarrayAccessorBase, XarrayMapper


class ObservationMapper(XarrayMapper[ObservationSchema]):
    pass


@xr.register_dataset_accessor("observation")
@xr.register_datatree_accessor("observation")
class ObservationAccessor(XarrayAccessorBase[ObservationMapper]):
    @property
    def signal(self) -> xr.DataArray:
        return self.mapper.get_arr(
            self.data_source,
            self.mapper.schema.signal,
        )
```

The mapper accepts three source forms:

| Source | Lookup surface |
| --- | --- |
| `Dataset` | Data variables, coordinates, and Dataset attributes |
| `DataArray` | Its named payload, coordinates, and DataArray attributes |
| `DataTree` | The Dataset at the current node; child nodes are not searched |

A domain accessor that owns a DataTree hierarchy should select its child node
before calling the mapper. Generic recursive lookup would make repeated field
names in different nodes ambiguous.

### Read operations

- `get_arr(source, field)` returns the selected `DataArray` without converting
  its backing array. Labels, coordinates, attributes, and lazy backends are
  retained.
- `get_shape(source, field)` reads shape metadata through `get_arr()` and does
  not materialize array values.
- `get_value(source, field)` is the explicit raw-value boundary. Attributes are
  returned directly; arrays are converted with `DataArray.to_numpy()` and may
  therefore compute a lazy backend.
- `get_scalar(source, field)` returns an attribute or a scalar value. Reading a
  lazy array scalar necessarily computes that value.
- `has_arr(source, field)` and `has_attr(source, field)` distinguish the two
  storage categories for an already-resolved field.

If an attribute and an array have the same name, generic `get_value()` and
`get_scalar()` prefer the attribute. `get_arr()` explicitly selects only an
array payload, data variable, or coordinate.

### Container normalization

`ensure_dataset()` gives accessors one Dataset-shaped interface:

- a Dataset is returned unchanged;
- a DataTree becomes its current-node Dataset; and
- a DataArray is wrapped as a one-variable Dataset.

The DataArray wrapper retains enough private metadata for
`unwrap_data_source()` to recover the payload and its attribute surface during
mapper operations. Callers should not inspect or depend on that private
metadata. `ensure_datatree()` provides the corresponding normalization to a
DataTree while preserving the same mapper behavior.

### Units

Importing `tollan.accessor.xarray` registers the `u` accessor on DataArray.
Units are stored as strings in `DataArray.attrs["units"]` and interpreted with
Astropy.

- `.u.unit` returns the Astropy unit, or `None` when no unit is set.
- `.u.set(unit)` and `.u.unset()` return shallow copies by default; pass
  `inplace=True` for explicit attribute mutation.
- `.u.to(unit)` returns a DataArray with converted values and unit metadata.
- `.u.quantity` returns an Astropy Quantity when units are present and the
  original DataArray when they are absent.

## netCDF4

`NetCDF4Mapper` adapts a `netCDF4.Dataset` to the generic mapper interface.
Define a concrete schema binding and resolve it against an open Dataset:

```python
from tollan.accessor.netcdf4 import NetCDF4Mapper


class ObservationNetCDFMapper(NetCDF4Mapper[ObservationSchema]):
    pass


mapper = ObservationNetCDFMapper.from_data_source(dataset)
signal = mapper.get_value(dataset, mapper.schema.signal)
observation_id = mapper.get_value(dataset, mapper.schema.observation_id)
```

This adapter provides raw reads rather than xarray-style labeled reads.
Variable values are returned as NumPy arrays, and attributes are returned as
array representations. Keep the netCDF4 Dataset open for resolution and reads.

## pandas DataFrame

`DataFrameMapper` resolves schema names against DataFrame columns and
`DataFrame.attrs`:

```python
from tollan.accessor.pandas import DataFrameMapper


class ObservationFrameMapper(DataFrameMapper[ObservationSchema]):
    pass


mapper = ObservationFrameMapper.from_data_source(frame)
signal = mapper.get_value(frame, mapper.schema.signal)
observation_id = mapper.get_value(frame, mapper.schema.observation_id)
```

Columns are returned through `Series.to_numpy()`, so the result does not retain
the pandas index. Values from `DataFrame.attrs` are returned unchanged. When an
attribute and a column share a name, the attribute takes precedence.

## API reference

- {class}`tollan.accessor.xarray.XarrayMapper`
- {class}`tollan.accessor.xarray.XarrayAccessorBase`
- {class}`tollan.accessor.xarray.UnitsAccessor`
- {class}`tollan.accessor.netcdf4.NetCDF4Mapper`
- {class}`tollan.accessor.pandas.DataFrameMapper`
