# Schema, mapping, and accessor design

Tollan separates the scientific meaning of a field from the name and structure
used by a storage format. A schema defines the scientific vocabulary, a mapper
resolves that vocabulary for a data source, and an accessor presents the
resulting data through a domain-oriented API.

## Core model

| Object | Responsibility |
| --- | --- |
| `Schema` | Declares a flat set of semantic fields |
| `Mapping` | Defines the strategy interface for resolving one field |
| `NameMapping` | Resolves a field from ordered physical-name candidates |
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
    signal: Mapping = NameMapping(("signal", "Data.Signal"))
    timestamp: Mapping = NameMapping(("time", "timestamp"))
```

Schemas are flat catalogs. Related fields can share a schema without creating
nested access paths. This keeps each field reference stable and makes mapper
resolution order explicit.

`NameMapping` tries its names in declaration order. The first name supported by
the source becomes the physical name in the concrete mapping plan.

## Mapper resolution

`Mapper.from_data_source(source)` resolves schema fields in declaration order.
For each field, it calls the field's `Mapping.resolve(context)` method and uses
the returned `NameMapping` to probe the source.

```text
schema.signal
    │
    │ resolve(context)
    ▼
NameMapping(("signal", "Data.Signal"))
    │
    │ first available name
    ▼
MappedField(
    mapping=schema.signal,
    mapping_resolved=<the selected NameMapping>,
    name="Data.Signal",
    source=MappedFieldSource.DATA_SOURCE,
    value=MISSING,
)
```

The resulting `MappedField` records:

- `mapping`: the strategy declared on the schema;
- `mapping_resolved`: the concrete `NameMapping` selected by that strategy;
- `name`: the physical source name;
- `source`: whether the field came from the source, a default, or is missing;
- `value`: resolution metadata captured when `resolve_value=True`;
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
            return NameMapping("signal_complex")
        return NameMapping(("signal_real", "signal"))


@dataclass
class SignalSchema(Schema):
    signal: Mapping = SignalByRepresentation()
```

`resolve_value=True` is available for small fields whose values determine later
resolution decisions. Because fields resolve in declaration order, a later
strategy can read that value from `context.mapped_fields`.

The context belongs only to the resolution operation. The resulting mapper
retains the concrete plan, not the data source.

## Reading data

Read methods always receive the source explicitly:

```python
mapper = ObservationMapper.from_data_source(reference_source)

signal = mapper.get_arr(source, mapper.schema.signal)
timestamp = mapper.get_scalar(source, mapper.schema.timestamp)
```

This supports the established workflow in which a mapper is resolved once and
reused with sources that have the same storage structure.

The main lookup and read contracts are:

- `mapping in mapper` reports whether the field was present in the reference
  source used to build the plan;
- `get_name(mapping)` returns the resolved physical name, or `None` when the
  mapping is not part of the plan;
- `get_value(source, mapping)` reads data-source fields from `source`, returns
  mapper defaults for defaulted fields, and raises `KeyError` for missing or
  unrelated mappings;
- backend methods such as `get_arr` and `get_scalar` use the same concrete plan
  while preserving their backend-specific return and error behavior.

A value captured by `resolve_value=True` remains resolution metadata in the
`MappedField`; it does not replace a later read from the explicitly supplied
source.

## Backend implementations

`Mapper` provides two hooks for a storage backend:

```python
def _has_field(self, data_source, name: str) -> bool: ...
def _read_value(self, data_source, name: str): ...
```

The base implementations return `False` and `None`, which supports
name/default-only mapper construction. Concrete xarray, pandas, and NetCDF
mappers implement source-specific discovery and reading. They may also add
typed operations such as `get_arr`, `get_scalar`, shape checks, and coordinate
validation.

## Design invariants

- A schema is a flat, ordered collection of semantic mappings.
- A mapping strategy resolves to one immutable `NameMapping`.
- A concrete mapper records names, defaults, missing fields, and explicit
  resolution metadata.
- Ordinary source values are read on demand and are not stored in the mapper.
- The source used for resolution is not retained by the mapper.
- The concrete mapping plan is read-only to callers.
- Accessors use the mapper API rather than duplicating storage-name logic.
