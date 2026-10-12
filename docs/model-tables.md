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

Columns follow field order, then alias order, then type-rule output order.
Unmatched fields are skipped; generated aliases are not matched again.
Rule settings are validated at construction. Colliding final column names raise
an error. Use `|` to add or override explicit declarations in a generated mapping.

Custom type rules receive `(name, annotation, column_name)` and return a mapping
of final names to `ModelColumn` declarations, or None for no match. An empty
mapping stops selection without creating columns. Exceptions propagate.
Repeated callables and identically configured rule models raise a validation
error. Different configurations may overlap; the first matching rule wins.

Time formats, coordinate attributes, and units must be supplied when constructing
the corresponding rules. Coordinate attributes are read without transforming
frames; unavailable attributes raise an error. The `*_frame` column contains the
Astropy frame name, such as `"icrs"`, `"fk5"`, `"altaz"`, or `"galactic"`. Include
it in positional queries when rows may use different frames. List registered
frame names with:

```{testcode}
from astropy.coordinates import frame_transform_graph

frame_names = sorted(frame_transform_graph.get_names())
assert "icrs" in frame_names
```

## Derive values from ordered record rules

Use `RecordRuleMapper` to associate partial record patterns with values. The
first matching rule supplies the result; unmatched records receive `default`.
Each named field must equal its expected scalar value. Extra fields are ignored.

```{testcode}
from enum import Enum
from tollan.accessor.pandas.model_table import RecordRuleMapper

class Status(Enum):
    ready = "ready"
    incomplete = "incomplete"
    unknown = "unknown"

status_mapper = RecordRuleMapper[Status](
    [
        ({"channel": 1}, Status.ready),
        ({"amplitude": None}, Status.incomplete),
    ],
    default=Status.unknown,
)
assert status_mapper({"channel": 1, "amplitude": 2.5}) is Status.ready
assert status_mapper({"channel": 2, "amplitude": None}) is Status.incomplete
assert status_mapper({}) is Status.unknown

# Batch evaluation returns one value per row, regardless of index labels.
values = status_mapper.map_table(table)
assert values == [Status.ready, Status.incomplete]
table["status"] = values
assert table.status.iloc[0] is Status.ready
```

Rules are copied at construction and can be reused for multiple records and
tables. Result objects, including enum members and callables, are returned
unchanged. The mapper does not modify its input; assign the returned list to
install a column, choosing its pandas dtype as needed.

None constraints match null values, including NaN and `pandas.NA`, but not
missing fields or empty strings. Ellipsis imposes no constraint, and an empty
pattern matches every record. For tables with renamed fields, pass
`column_names={"channel": "file_channel"}` to `map_table`; rule names omitted
from that mapping are used unchanged.

Override `default` for one evaluation without changing the mapper:

```{testcode}
assert status_mapper({}, default=None) is None
assert status_mapper({}) is Status.unknown
```

To compare independent interpretations, callers can use a shared unmatched
marker and collect one column per mapper. Choose a marker that no matching rule
returns. In this example, all rule results are enum members, so None marks
unmatched rows:

```{testcode}
import pandas as pd

ready_mapper = RecordRuleMapper[Status](
    [({"channel": 1}, Status.ready)], default=Status.unknown,
)
incomplete_mapper = RecordRuleMapper[Status](
    [({"amplitude": None}, Status.incomplete)], default=Status.unknown,
)
candidates = pd.DataFrame({"channel": [1, 2, 1], "amplitude": [None, 2.0, 3.0]})
interpretations = pd.DataFrame({
    "ready": ready_mapper.map_table(candidates, default=None),
    "incomplete": incomplete_mapper.map_table(candidates, default=None),
}, index=candidates.index)
match_count = interpretations.notna().sum(axis=1)
assert match_count.tolist() == [2, 0, 1]
ambiguous = candidates.loc[match_count > 1]
assert ambiguous.index.tolist() == [0]
```

The caller decides how to handle multiple interpretations or no interpretation.
Within each mapper, the first matching rule still wins. `map_table` evaluates
constraints column-wise and reuses repeated comparisons instead of invoking the
scalar mapper for every row. For a fixed rule set, runtime remains linear in
the number of rows.

## Query the collected values

`query()` uses pandas expressions on the current columns, with the Python engine.
Use only trusted expressions. Subclasses can extend `_query_namespace` with
constants or query functions; existing column names take precedence.
For a plain DataFrame, {func}`tollan.utils.pandas.query` provides the same
helpers and accepts additional names through `namespace`.

Use `contains(column, value)` for exact element membership in list, tuple, set
or frozenset cells. Empty and missing collections return false; other cell types
raise `TypeError`. Strings are not treated as collections of characters, and
membership does not perform substring or regex matching. Pandas `in` and `isin`
compare whole cells rather than searching within each collection.

```{testcode}
memberships = pd.DataFrame({
    "tags": [["science", "reviewed"], ["engineering"], [], None],
    "exposure": [60, 30, 10, 0],
})
selected = ModelTableAccessor(memberships).query(
    'contains(tags, "science") and exposure > 30'
)
assert selected.index.tolist() == [0]
assert ModelTableAccessor(memberships).query(
    '~contains(tags, "science")'
).index.tolist() == [1, 2, 3]
```

The built-in `bits_any_set(column, mask)` and `bits_all_set(column, mask)` select
integer bitmasks or enum-valued object columns. Object columns require a mask of
the matching flag enum type; equal bit values from another enum never match.
Nulls remain unknown. See
{func}`~tollan.utils.pandas.bits_any_set` and
{func}`~tollan.utils.pandas.bits_all_set` for zero-mask behavior.
