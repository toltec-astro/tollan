# Schema, mapping, and accessor design

Tollan separates the meaning of a field from the name and structure
used by a storage format. A schema defines the semantic vocabulary, a mapper
resolves that vocabulary for a data source, and an accessor presents the
resulting data through a domain-oriented API.

## Core model

| Object | Responsibility |
| --- | --- |
| `Schema` | Declares a flat set of semantic fields |
| `Mapping` | Defines the strategy interface for resolving one field |
| `NameMapping` | Resolves a field from ordered name/location candidates |
| `FieldLocation` | Identifies an attribute, variable, or dimension namespace |
| `MappingContext` | Supplies the source, schema, and prior results during resolution |
| `MappedField` | Records the immutable result of resolving one field |
| `Mapper` | Holds a concrete mapping plan and implements source reads |
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

```python
from dataclasses import dataclass

from tollan.accessor import Mapping, NameMapping, Schema


@dataclass
class ObservationSchema(Schema):
    signal: Mapping = NameMapping.var(("signal", "Data.Signal"))
    timestamp: Mapping = NameMapping.var(("time", "timestamp"))
```

Schemas are flat catalogs. Related fields can share a schema without creating
nested access paths. This keeps each field reference stable and makes mapper
resolution order explicit.

`NameMapping.var(...)`, `.attr(...)`, and `.dim(...)` try one name or a sequence
of names at the specified location. Variables include coordinates and table
columns; dimensions return their integer lengths. A coordinate and its dimension
are separate fields:

```python
sample = NameMapping.var("sample")  # Coordinate values
n_samples = NameMapping.dim("sample")  # Dimension length
```

To try different locations in order, supply name/location pairs:

```python
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
must occur in at most one supported namespace. Ambiguous names raise `ValueError`
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
- `name`: the physical source name;
- `location`: the storage namespace used for subsequent reads;
- `source`: whether the original resolution found a source field, a default,
  or neither;
- `value`: resolution metadata captured when `resolve_value=True`;
- `value_default`: the configured fallback, or `MISSING` if none was supplied;
- `schema_path`: the semantic location of the field.

`mapper.mapped_fields` is a read-only view of this plan.

## Mapping context and conditional mappings

All fields resolved by one `from_data_source` call share a `MappingContext`.
It contains:

- `data_source`: the source being resolved;
- `schema`: the mapper's schema instance;
- `mapped_fields`: a read-only view of fields resolved earlier in declaration
  order.

A custom strategy may use any of this information to return a `NameMapping`:

```python
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
retains the concrete plan, not the data source.

## Reading data

Read methods always receive the source explicitly:

```python
mapper = ObservationMapper.from_data_source(reference_source)

signal = mapper.get_var(source, mapper.schema.signal)
timestamp = mapper.get_var(source, mapper.schema.timestamp)
```

This supports the established workflow in which a mapper is resolved once and
reused with sources that have the same storage structure.
Reads use the recorded name and location without trying candidates again. If
that field disappears from a later source, a same-named field in another
namespace does not replace it. Resolve a new mapper to choose a different plan.

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

```python
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

The public methods accept schema fields and handle candidate ordering, location
dispatch, and defaults. To give `get_var()` a precise return type, supply the
native variable type as the third generic argument, for example
`Mapper[MySchema, MySource, MyVariable]`. Defaults for the source and variable
type arguments are `Any`.

## Design invariants

- A schema is a flat, ordered collection of semantic mappings.
- A mapping strategy resolves to one immutable `NameMapping`.
- A concrete mapper records names, defaults, missing fields, and explicit
  resolution metadata.
- Ordinary source values are read on demand and are not stored in the mapper.
- The source used for resolution is not retained by the mapper.
- The concrete mapping plan is read-only to callers.
- Accessors use the mapper API rather than duplicating storage-name logic.
