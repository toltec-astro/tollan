# Schemas, mappings, and accessors

Tollan separates the meaning of a field from the name and structure
used by a storage format. A schema defines the semantic vocabulary, a mapper
resolves that vocabulary for a data source, and an accessor presents the
resulting data through a domain-oriented API.

## Core model

| Object | Responsibility |
| --- | --- |
| `Schema` | Gives consistent names to entities that may occur in data |
| `Mapping` | Defines the strategy interface for resolving one field |
| `NameMapping` | Declares candidate names, entity kinds, and a containing subtree |
| `FieldLocation` | Identifies the entity kind: attribute, variable, dimension, or subtree |
| `MappingContext` | Supplies the source, schema, and prior results during resolution |
| `MappedField` | Records the immutable result of resolving one field |
| `Mapper` | Probes the data layout and provides access using the schema vocabulary |
| `AccessorBase` | Exposes domain-level operations over a source and mapper |

The normal data path is:

```text
Schema declaration
       │
       ▼
Mapper.from_data_source(reference_source)
       │
       ▼
Concrete mapping plan: semantic field → MappedField
       │
       ▼
mapper.get_*(source, schema.field)
       │
       ▼
Accessor properties and domain operations
```

## Schema declarations

Schemas are standard-library dataclasses. Each field is annotated with
`Mapping`, allowing either a `NameMapping` or another mapping strategy.

```{testcode}
from dataclasses import dataclass

from tollan.accessor import Mapping, NameMapping, Schema


@dataclass
class ObservationSchema(Schema):
    signal: Mapping = NameMapping.var(("signal", "Data.Signal"))
    timestamp: Mapping = NameMapping.var(("time", "timestamp"))
```

Fields resolve in declaration order. A conditional mapping can use the results
of fields declared before it.

`NameMapping.var(...)`, `.attr(...)`, `.dim(...)`, and `.path(...)` declare
candidate names or paths for one entity kind. The mapper selects the first
existing candidate. Variables include coordinates and table columns; dimension
reads return integer lengths. A coordinate and its dimension are separate fields:

```{testcode}
sample = NameMapping.var("sample")  # Coordinate values
n_samples = NameMapping.dim("sample")  # Dimension length
```

### Subtree paths

Use path mappings to identify subtrees by a consistent schema field name.
`mapper.get_node()` returns the mapped subtree without copying it or loading
its arrays:

```{testcode}
import xarray as xr
from tollan.accessor.xarray import XarrayMapper


@dataclass
class SpectrumSchema(Schema):
    result: Mapping = NameMapping.path(("analysis/spectrum", "spectrum", "."))
    power: Mapping = result / NameMapping.var("power")


class SpectrumMapper(XarrayMapper[SpectrumSchema]):
    pass


tree = xr.DataTree.from_dict({
    "measurement/analysis/spectrum": xr.Dataset({"power": ("frequency", [1., 2.])})
})
scope = tree["measurement"]
mapper = SpectrumMapper.from_data_source(scope)
result = mapper.get_node(scope, mapper.schema.result)
assert result is scope["analysis/spectrum"]
assert mapper.get_arr(scope, mapper.schema.power).sizes == {"frequency": 2}

detached = scope.copy(deep=False)
assert mapper.get_node(detached, mapper.schema.result) is detached["analysis/spectrum"]
```

Relative paths start at the supplied node; `.` selects that node. Absolute paths
start at the containing tree's root. Prefer relative paths for subtrees that
should remain usable when detached. A path mapping cannot resolve to a variable,
even if indexing that path would return a DataArray. Flat Dataset and DataArray
sources have no nodes.

A field's `parent` declares the subtree containing it. The `/` operator is
shorthand for the same declaration:

```{testcode}
assert SpectrumSchema.power == NameMapping.var("power", parent=SpectrumSchema.result)
```

Declare each parent as a schema field before its children; inherited field
overrides retain that order. Invalid parent references raise `ValueError` when
constructing the mapper.

The first existing parent path applies to all its child fields. Their name
candidates are tried within that node; a missing field does not select another
parent. Reads use the same path on the source supplied to the read, so a mapper
can also read a detached copy. `get_name()` returns the local field name.
`from_defaults()` selects the first candidate for each parent path and child name.

Parent mappings work for variables, coordinates, attributes, dimensions, and
child paths. Coordinates use `NameMapping.var()`. A direct variable mapping such
as `NameMapping.var("analysis/spectrum/power")` also works on DataTrees. For
attributes and dimension sizes, use a parent mapping with the local attribute
or dimension name. Backends without subtree support reject parent mappings.

Override a parent field to read its children from a different subtree:

```{testcode}
@dataclass
class AlternateSpectrumSchema(SpectrumSchema):
    result: Mapping = NameMapping.path("products/spectrum")


class AlternateSpectrumMapper(XarrayMapper[AlternateSpectrumSchema]):
    pass


alternate = xr.DataTree.from_dict({
    "products/spectrum": xr.Dataset({"power": ("frequency", [3., 4.])})
})
other_mapper = AlternateSpectrumMapper.from_data_source(alternate)
assert other_mapper.get_arr(alternate, other_mapper.schema.power).values.tolist() == [3., 4.]
```

A custom `Mapping.resolve()` can select a declared parent at resolution time by
returning a `NameMapping` with that parent. Parent lookup follows the same schema
overrides as a direct declaration.

Compose deeper paths through named schema fields:

```{testcode}
@dataclass
class NestedSpectrumSchema(Schema):
    namespace: Mapping = NameMapping.path("analysis")
    result: Mapping = namespace / NameMapping.path("spectrum")
    power: Mapping = result / NameMapping.var("power")
```

Use `SubpathMapping` when every candidate must be a descendant of the supplied
node. It validates paths when the schema is declared:

```{testcode}
from tollan.accessor import SubpathMapping

input_subpath = SubpathMapping.path(("samples", "_input"))
assert input_subpath.names == ("samples", "_input")
```

Absolute paths, empty components, `.` and `..` are invalid for `SubpathMapping`.
Use `NameMapping.path()` when those general tree selectors are needed.

To try different locations in order, supply name/location pairs:

```{testcode}
from tollan.accessor import FieldLocation

n_samples = NameMapping(
    [
        ("sample", FieldLocation.dim),
        ("sample_count", FieldLocation.attr),
    ]
)
```

The first existing pair is recorded in the concrete plan. The same name may
appear at different locations; duplicate pairs are rejected. `.names` returns
the candidate names in order, for example when choosing names for output data.

Bare names, such as `NameMapping("version")`, infer their location. Each name
must identify at most one supported entity kind. Ambiguous names raise `ValueError`
at resolution, rather than advancing to the next candidate. Specify a location
when a name is shared by an attribute and variable, or a coordinate and dimension.

## Mapper resolution

`Mapper.from_data_source(source)` resolves schema fields in declaration order.
For each field, it calls the field's `Mapping.resolve(context)` method and uses
the returned `NameMapping` to probe the source.

```text
schema.signal
    │
    │ resolve(context)
    ▼
NameMapping.var(("signal", "Data.Signal"))
    │
    │ first available name
    ▼
MappedField(
    mapping=schema.signal,
    mapping_resolved=<the selected NameMapping>,
    name="Data.Signal",
    location=FieldLocation.var,
    source=MappedFieldSource.data_source,
    value=MISSING,
)
```

The resulting `MappedField` records:

- `mapping`: the strategy declared on the schema;
- `mapping_resolved`: the concrete `NameMapping` selected by that strategy;
- `name`: the physical name within the selected source;
- `parent_path`: the containing subtree path, or `None` for the supplied source;
- `location`: the entity kind used for subsequent reads;
- `source`: whether the original resolution found a source field, a default,
  or neither;
- `value`: resolution metadata captured when `resolve_value=True`;
- `value_default`: the configured fallback, or `MISSING` if none was supplied;
- `schema_path`: the diagnostic identifier `SchemaClass.attribute`.

`mapper.mapped_fields` is a read-only view of this plan.

## Mapping context and conditional mappings

Each field resolves with a `MappingContext` containing:

- `data_source`: the source being resolved;
- `schema`: the mapper's schema instance;
- `mapped_fields`: a read-only view of fields resolved earlier in declaration
  order.

A custom strategy may use any of this information to return a `NameMapping`:

```{testcode}
from dataclasses import dataclass

from tollan.accessor import Mapping, MappingContext, NameMapping, Schema


@dataclass(frozen=True)
class SignalByRepresentation(Mapping):
    def resolve(self, context: MappingContext) -> NameMapping:
        if context.data_source.attrs.get("representation") == "complex":
            return NameMapping.var("signal_complex")
        return NameMapping.var(("signal_real", "signal"))


@dataclass
class SignalSchema(Schema):
    signal: Mapping = SignalByRepresentation()
```

`resolve_value=True` is available for small fields whose values determine later
resolution decisions. Because fields resolve in declaration order, a later
strategy can read that value from `context.mapped_fields`.
Eager resolution captures the source value when present, otherwise the configured
fallback. With neither available, `value` remains `MISSING`. Fields without
`resolve_value=True` keep `value=MISSING`, even when they have a fallback;
the fallback is stored separately in `value_default`.

The context belongs only to the resolution operation. The resulting mapper
retains the concrete plan. Ordinary resolution does not retain the data source;
explicitly capturing a node with `resolve_value=True` retains that native subtree
and its parent relationship, without loading any arrays.

## Reading data

Read methods always receive the source explicitly:

```{testcode}
class ObservationMapper(XarrayMapper[ObservationSchema]):
    pass


reference_source = xr.Dataset({
    "Data.Signal": ("sample", [1.0, 2.0]),
    "timestamp": ("sample", [0.0, 1.0]),
})
mapper = ObservationMapper.from_data_source(reference_source)
source = reference_source.copy(deep=True)
source["Data.Signal"] = source["Data.Signal"] * 2
signal = mapper.get_var(source, mapper.schema.signal)
timestamp = mapper.get_var(source, mapper.schema.timestamp)
assert signal.values.tolist() == [2.0, 4.0]
assert timestamp.values.tolist() == [0.0, 1.0]
```

Reuse a mapper with sources that have the same field names and locations.
Reads use the recorded mapping without trying candidates again. If
that field disappears from a later source, a same-named entity of another kind
does not replace it. Resolve a new mapper to select different data locations.

The main lookup and read contracts are:

- `mapping in mapper` reports whether the field was present in the reference
  source used to build the plan;
- `get_name(mapping)` returns the resolved physical name, or `None` when the
  mapping is not part of the plan;
- `get_value(source, mapping)` reads the field at its recorded source location,
  without substituting a fallback;
- `get_value_or_default(source, mapping)` reads the source field when present,
  otherwise returns `value_default`. It raises `KeyError` if neither is available
  or the mapping is unrelated, and propagates source read errors;
- `get_var()` returns the native variable without loading its values;
- `get_scalar()` and `get_str()` read scalar and text fields according to the
  source's supported representations. See the [read-method table](data-adapters.md#choose-a-read-method)
  for return values and loading behavior.

A value captured by `resolve_value=True` remains resolution metadata in the
`MappedField`; it does not replace a later read from the explicitly supplied
source.
Defaults remain available even if the reference source has the field. See
[optional-field fallbacks](data-adapters.md#supply-a-fallback-for-an-optional-field)
for an example and handling of fields with no resolved location.

## Writing a mapper for another source type

Bind your schema and source type to `Mapper`, then implement existence checks
and reads for the locations your source supports. For a dictionary-like source,
implement `_has_var()` and `_get_var()`:

```{testcode}
from typing import Any

from tollan.accessor import Mapper


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
