# Write a mapper for another source type

This page is for developers who add a source type to the
{doc}`schema, mapping and accessor <schema-mapping-accessors>` system. Users of
the existing backends do not need it.

Bind your schema and source type to `Mapper`, then implement existence checks
and reads for the locations your source supports. For a dictionary-like source,
implement `_has_var()` and `_get_var()`:

```{testcode}
from dataclasses import dataclass
from typing import Any

from tollan.accessor import Mapper, Mapping, NameMapping, Schema


@dataclass
class ObservationSchema(Schema):
    signal: Mapping = NameMapping.var(("signal", "Data.Signal"))
    timestamp: Mapping = NameMapping.var(("time", "timestamp"))


class DictMapper(Mapper[ObservationSchema, dict[str, Any]]):
    def _has_var(self, data_source: dict[str, Any], name: str) -> bool:
        return name in data_source

    def _get_var(self, data_source: dict[str, Any], name: str) -> Any:
        return data_source[name]


source = {"Data.Signal": [1, 2, 3], "timestamp": [0, 1, 2]}
mapper = DictMapper.from_data_source(source)
assert mapper.get_value(source, mapper.schema.signal) == [1, 2, 3]
```

Implement these hooks for your source type:

| Hook | Result | Loading contract |
| --- | --- | --- |
| `_has_attr(source, name)`, `_has_var(source, name)`, `_has_dim(source, name)` | Whether a physical name exists at that location | Do not load variable values |
| `_get_attr(source, name)` | Attribute value, unchanged | Retrieve metadata, not array values |
| `_get_dim(source, name)` | Current integer dimension length | Do not load coordinates or other variable values |
| `_get_var(source, name)` | Native variable object | Preserve its backend and do not request its values |
| `_has_node(source, path)`, `_get_node(source, path)` | Subtree existence and native subtree | Do not copy or load descendant arrays |
| `_read_var_values(var)` | Values from the native variable | May perform substantial I/O or computation |
| `_read_scalar_var(var)` | One scalar value | Check shape before reading |
| `_read_str_var(var)` | Values representing one string, before decoding | Check shape and dtype before reading |

The lookup hooks receive physical names, not schema fields. The read hooks
receive the native variable already retrieved by `_get_var()`. For example,
an xarray backend implements `_read_var_values(var)` with `var.to_numpy()`;
a netCDF4 backend uses `var[...]`.

For plain-value sources such as the dictionary above, the default
`_read_var_values()` returns its input unchanged. Scalar and string variable
reads raise `ValueError` unless the backend implements their hooks. Attribute
reads and dimension reads use the shared implementation. `get_str()` performs
the final decoding and padding removal for attributes and variables.

For a source with additional locations, declare `_supported_locations`, for
example `(FieldLocation.attr, FieldLocation.var, FieldLocation.dim)`, and implement
the corresponding hooks. By default only `var` is supported, and all existence
hooks return `False`. `from_defaults()` does not require source reads.

Implement the hooks using data names and paths; callers use schema fields with
the public methods. To give `get_var()` a precise return type, supply the native
variable type as the third generic argument, for example
`Mapper[MySchema, MySource, MyVariable]`. Defaults for the source and variable
type arguments are `Any`.
