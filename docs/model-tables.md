# Build and query model tables

Use `ModelTableAccessor` to collect selected attributes into a pandas DataFrame,
add information in later passes, and filter rows. Inputs can be Pydantic models,
dataclasses, or other objects with the declared attributes. You can consume the
result with normal pandas operations, including `itertuples()`.

## Project selected attributes

Declare each output column with its attribute path and, optionally, a default,
converter, and pandas dtype. Unspecified dtypes retain Python objects.

```{testcode}
from types import SimpleNamespace

from tollan.accessor.pandas import ModelTableAccessor
from tollan.accessor.pandas.model_table import ModelColumn

columns = {
    "channel": ModelColumn("channel", dtype="Int64"),
    "amplitude": ModelColumn("reading.amplitude", default=None, dtype="Float64"),
}
samples = [
    SimpleNamespace(channel=1, reading=SimpleNamespace(amplitude=2.5)),
    SimpleNamespace(channel=2),
]
table = ModelTableAccessor.from_models(samples, columns=columns)
assert table.channel.tolist() == [1, 2]
assert table.amplitude.isna().tolist() == [False, True]
selected = ModelTableAccessor(table).query("amplitude > 1")
assert next(selected.itertuples(index=False)).channel == 1
```

Only declared attributes are read; projection does not call `model_dump()`.
Missing required attributes raise `AttributeError`. Defaults follow
{func}`~tollan.utils.py.rgetattr`; a present `None` is not replaced by a default
or passed to a converter. Empty input retains the declared columns and dtypes.

## Add or replace information

An update accepts either one object per table row or a mapping from integer row
positions to objects. Positions follow `iloc`, including negative indices; index
labels do not affect which rows are updated.

```{testcode}
updated = ModelTableAccessor(table).update_from_models(
    {1: SimpleNamespace(amplitude=0.5)},
    columns={"amplitude": ModelColumn("amplitude", dtype="Float64")},
)
assert updated.amplitude.tolist() == [2.5, 0.5]
assert table.amplitude.isna().tolist() == [False, True]

result = ModelTableAccessor(table).update_from_models(
    [SimpleNamespace(checked=True), SimpleNamespace(checked=False)],
    columns={"checked": ModelColumn("checked", dtype="boolean")},
    inplace=True,
)
assert result is None
assert table.checked.tolist() == [True, False]
```

Updates return a copy unless `inplace=True`. Null projections overwrite existing
values. Untouched rows, unrelated columns, the index, and table attributes remain
unchanged. Existing column dtypes remain unchanged; incompatible assignments
raise. New columns use the declared dtype, which must support missing values.

A sequence must match the table length. Mapping keys must address distinct rows:
for a three-row table, `-1` and `2` cannot both be supplied. Slices and broadcasting
are not supported. In-place updates are not transactional: an assignment error
may leave earlier columns updated.

## Generate declarations from model annotations

`ModelColumnMapper` prepares column declarations from a Pydantic model class.
Supply both name rules and type rules explicitly. Every matching name regex
contributes an alias; duplicate aliases are removed in rule order. The first
matching type rule determines each alias's representation.

```{testcode}
from astropy.time import Time
from pydantic import BaseModel
from tollan.config.types import TimeQuantityField, UnixTimeField
from tollan.accessor.pandas.model_table import (
    ModelColumnMapper, QuantityColumnRule, ScalarColumnRule, TimeColumnRule,
)

class Reading(BaseModel):
    channel: int
    timestamp: UnixTimeField
    duration: TimeQuantityField

mapper = ModelColumnMapper(
    name_rules=[(r".+", r"\g<0>")],
    type_rules=[
        TimeColumnRule(format="mjd"),
        QuantityColumnRule(physical_type="time", unit="s"),
        ScalarColumnRule(),
    ],
)
reading = Reading(channel=1, timestamp=Time(60000, format="mjd"), duration="2 s")
readings = ModelTableAccessor.from_models([reading], columns=mapper(Reading))
assert list(readings) == ["channel", "timestamp_mjd", "duration_s"]
assert readings.timestamp_mjd.tolist() == [60000]
assert readings.duration_s.tolist() == [2]
```

Name rules full-match original field names; `exclude` rejects matching
names. `model_path` supplies a dotted parent attribute path without changing the
output names. `include_computed=True` includes computed-field annotations.
Declaration generation does not read instances. Reuse the resulting mapping
across batches of compatible objects, including objects of different classes.

Scalar rules include primitive scalar fields and enum values. Quantity rules
include fields with the specified physical type and append the chosen unit to
the column name. Time rules append the requested format and preserve each time
value's scale. `SkyCoordColumnRule(attrs=["ra", "dec"], unit="deg")` produces
angular columns plus a frame-name column; values must provide those attributes.
Nested objects and arrays require explicit declarations.

## Query the collected values

`query()` uses pandas expressions on the current columns, with the Python engine.
Use only trusted expressions. Subclasses can extend `_query_namespace` with
constants or query functions; existing column names take precedence.

The built-in `bits_any_set(column, mask)` and `bits_all_set(column, mask)` select
integer bitmasks or enum-valued object columns. Object columns require a mask of
the matching flag enum type; equal bit values from another enum never match.
Nulls remain unknown. See
{meth}`~tollan.accessor.pandas.ModelTableAccessor.query` for zero-mask behavior.
