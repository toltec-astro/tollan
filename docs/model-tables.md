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
or passed to a converter. A non-None default is passed to the converter.
Empty input retains the declared columns and dtypes.

### Choose a dtype and converter

Choose a dtype that can represent your values without loss. Boolean, integer,
floating-point and complex columns reject truncation, overflow and precision
loss. For example, writing `1.5` to an integer column raises instead of silently
discarding the fraction. To round values, supply a converter explicitly:

```{testcode}
rounded = ModelTableAccessor.from_models(
    [SimpleNamespace(value=1.5)],
    columns={"value": ModelColumn("value", dtype="int64", converter=round)},
)
assert rounded.value.tolist() == [2]
```

The dtype must represent the converter's result exactly, including when the
input comes from a default. Use `converter=int` or `converter=float` to parse
numeric text; declaring a numeric dtype alone does not parse it.

Use a nullable dtype such as `Int64` or `boolean` when nulls are possible; nulls
are not converted to numbers or boolean values. Leave `dtype` unspecified to
retain Python objects. Other dtype conversions follow pandas behavior.

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

### Populate one column from different inputs

Each call supplies its own projection. Different attribute paths and converters
can populate the same column; they do not need to be combined into one mapping.
For example, collect counts from objects with a direct integer attribute and
from records with a nested string value:

```{testcode}
counts = ModelTableAccessor.from_models(
    [SimpleNamespace(label=name) for name in ("a", "b", "c")],
    columns={"label": ModelColumn("label", dtype="string")},
)
direct_columns = {"count": ModelColumn("count", dtype="Int64")}
stored_columns = {
    "count": ModelColumn("summary.total", converter=int, dtype="Int64"),
}
accessor = ModelTableAccessor(counts)
accessor.update_from_models(
    {0: SimpleNamespace(count=10), 2: SimpleNamespace(count=30)},
    columns=direct_columns,
    inplace=True,
)
assert counts["count"].isna().tolist() == [False, True, False]
accessor.update_from_models(
    {1: SimpleNamespace(summary=SimpleNamespace(total="20"))},
    columns=stored_columns,
    inplace=True,
)
assert counts["count"].tolist() == [10, 20, 30]
assert str(counts["count"].dtype) == "Int64"
```

A mapping declares one reader per output column for that call. If objects share
the declared attributes, they can use one projection even when their classes
differ. Otherwise, group the objects by the projection you want to apply and
update their row positions in batches. The accessor does not choose a projection
from each object's type. A later write to the same cell replaces its earlier
value; apply authoritative information after estimates.

The column's dtype constrains the values it can hold, not where they came from.
Each projection applies its declared dtype before assignment. When updating an
existing column, its dtype is retained even if the projection declares a
different dtype. Incompatible assignments raise; columns are not automatically
widened to `object`.

### Distinguish missing attributes, null values, and untouched cells

| Situation | Result |
| --- | --- |
| A declared attribute is missing | Read using `ModelColumn.default`, or raise if no default was supplied. |
| A projection produces None | Write a null, replacing any earlier value. |
| An existing column is omitted from the projection | Leave that column unchanged. |
| A row is absent from the positional update | Leave its existing values unchanged. |
| A new column has rows outside the update | Fill those rows with the dtype's missing value, not `ModelColumn.default`. |

For example, `default=0` supplies a value for a missing attribute in a selected
object. It does not fill unselected rows with zero:

```{testcode}
accessor.update_from_models(
    {1: SimpleNamespace()},
    columns={"attempts": ModelColumn("attempts", default=0, dtype="Int64")},
    inplace=True,
)
assert counts.attempts.iloc[1] == 0
assert counts.attempts.isna().tolist() == [True, False, True]

accessor.update_from_models(
    {1: SimpleNamespace(count=None)}, columns=direct_columns, inplace=True,
)
assert counts["count"].isna().tolist() == [False, True, False]
assert counts.label.tolist() == ["a", "b", "c"]
```

Using `default=None` also writes a null when the declared attribute is absent.
To preserve an existing value, omit that column or row from the update instead.

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
reading_columns = mapper(Reading)
reading = Reading(channel=1, timestamp=Time(60000, format="mjd"), duration="2 s")
readings = ModelTableAccessor.from_models([reading], columns=reading_columns)
assert list(readings) == ["channel", "timestamp_mjd", "duration_s"]
assert readings.timestamp_mjd.tolist() == [60000]
assert readings.duration_s.tolist() == [2]
```

Name rules full-match original field names; `exclude` rejects matching
names. `model_path` supplies a dotted parent attribute path without changing the
output names. `include_computed=True` includes computed-field annotations.
Declaration generation does not read instances. Reuse the resulting mapping,
such as `reading_columns`, across batches of compatible objects, including
objects of different classes. Each call to `mapper(Reading)` generates
declarations again; keeping the mapper instance alone does not reuse that result.

Scalar rules include primitive scalar fields and enum values. Quantity rules
include fields with the specified physical type and append the chosen unit to
the column name. Time rules append the requested format and preserve each time
value's scale. `SkyCoordColumnRule(attrs=["ra", "dec"], unit="deg")` produces
angular columns plus a frame-name column; values must provide those attributes.
Nested objects and arrays require explicit declarations.

Use `ExplicitColumnRule` to give selected fields their own declarations while
keeping the mapper's name rules. Its keys are exact original field names, not
output aliases; unlisted fields fall through to later rules. Put it before
annotation-based rules when it should override them:

```{testcode}
from tollan.accessor.pandas.model_table import ExplicitColumnRule

class TaggedEntry(BaseModel):
    tags: list[str]
    count: int

tagged_columns = ModelColumnMapper(
    name_rules=[(r".+", r"item_\g<0>"), (r"tags", r"\g<0>")],
    type_rules=[
        ExplicitColumnRule(columns={
            "tags": ModelColumn("tags", dtype=object, converter=list),
        }),
        ScalarColumnRule(),
    ],
    default=None,
)(TaggedEntry)
entry = TaggedEntry(tags=["ready"], count=2)
tagged = ModelTableAccessor.from_models([entry], columns=tagged_columns)
assert list(tagged) == ["item_tags", "tags", "item_count"]
assert tagged.tags.iloc[0] == ["ready"]
assert tagged.tags.iloc[0] is not entry.tags
```

The rule uses each selected alias as the output name. The declaration's `attr`
may differ from the matched field name. As with other rules, `model_path` prefixes
that read path and the mapper's `default` supplies missing-attribute behavior.
Only fields selected by the name rules and not excluded are considered.

Columns follow field order, then alias order, then type-rule output order.
Unmatched fields are skipped; generated aliases are not matched again.
Rule settings are validated at construction. Colliding final column names raise
an error. Use `|` to add or intentionally override explicit declarations within
one projection. It replaces declarations with the same key; it does not preserve
alternative readers for a column. For inputs needing different readers, use
[separate projections](#populate-one-column-from-different-inputs).

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

### Reuse projections across batches

Prepare column mappings outside row-processing loops, and pass batches to
`from_models()` or `update_from_models()`. Keep a separate mapping for each input
representation you need. This avoids repeating declaration generation and table
updates for individual objects.

Projection still reads and converts each selected value; it does not vectorize
arbitrary attribute access or converter functions. Expensive properties and
converters therefore affect every batch. For calculations on values already in
the table, use pandas column operations or `RecordRuleMapper.map_table()`.

## Derive values from ordered record rules

Use `RecordRuleMapper` to associate partial record patterns with values. The
first matching rule supplies the result; unmatched records receive `default`.
Plain constraint values test scalar equality; `Contains` tests membership in
collection-valued fields. All constraints in a rule must match. Extra fields are ignored.
Records may be mappings or objects: mappings use keys; other objects use
attributes, including models and rows from `DataFrame.itertuples()`.

```{testcode}
from enum import Enum
from tollan.accessor.pandas.model_table import RecordRuleMapper

class Status(Enum):
    ready = "ready"
    incomplete = "incomplete"
    unknown = "unknown"

status_mapper = RecordRuleMapper[Status](
    rules=[
        ({"channel": 1}, Status.ready),
        ({"amplitude": None}, Status.incomplete),
    ],
    default=Status.unknown,
)
assert status_mapper({"channel": 1, "amplitude": 2.5}) is Status.ready
assert status_mapper({"channel": 2, "amplitude": None}) is Status.incomplete
assert status_mapper({}) is Status.unknown
from types import SimpleNamespace
assert status_mapper(SimpleNamespace(channel=1)) is Status.ready

# Batch evaluation returns one value per row, regardless of index labels.
values = status_mapper.map_table(table)
assert values == [Status.ready, Status.incomplete]
table["status"] = values
assert table.status.iloc[0] is Status.ready
```

Rule declarations are validated and copied at construction and can be reused
for multiple records and tables. Validated result objects, including enum
members and callables, are returned unchanged. The mapper does not modify its
input; assign the returned list to install a column, choosing its pandas dtype
as needed.

None constraints match null values, including NaN and `pandas.NA`, but not
missing fields or empty strings. Ellipsis imposes no constraint, and an empty
pattern matches every record. For tables with renamed fields, pass
`column_names={"channel": "file_channel"}` to `map_table`; rule names omitted
from that mapping are used unchanged.

Use `Contains(value=...)` when a record field holds a collection:

```{testcode}
import pandas as pd
from tollan.accessor.pandas.model_table import Contains

action_mapper = RecordRuleMapper[str](
    rules=[
        ({"format": "nc", "tags": Contains(value="science")}, "analyze"),
        ({"tags": Contains(value="reviewed")}, "archive"),
    ],
    default="skip",
)
assert action_mapper({"format": "nc", "tags": ["science", "reviewed"]}) == "analyze"
assert action_mapper({"tags": []}) == "skip"
actions = action_mapper.map_table(pd.DataFrame({
    "format": ["nc", "ecsv", "nc"],
    "tags": [["science", "reviewed"], ["reviewed"], None],
}))
assert actions == ["analyze", "archive", "skip"]
```

Membership uses the same exact-element semantics as
{func}`tollan.utils.pandas.contains`. Lists, tuples, sets, frozensets and NumPy
arrays are supported. Missing, null and empty collections do not match;
non-null values of other types raise `TypeError`. In particular, a string is not
a collection cell, and string elements are not searched by substring or regex.

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
    rules=[({"channel": 1}, Status.ready)], default=Status.unknown,
)
incomplete_mapper = RecordRuleMapper[Status](
    rules=[({"amplitude": None}, Status.incomplete)], default=Status.unknown,
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

## Specialize rule results

Use a generic parameter to validate result values when constructing a mapper.
A subclass can fix that type and supply a default:

```{testcode}
class StatusMapper(RecordRuleMapper[Status]):
    default: Status | None = None

typed_mapper = StatusMapper.model_validate({
    "rules": [({"channel": 1}, "ready")],
})
assert typed_mapper({"channel": 1}) is Status.ready
assert typed_mapper({}) is None
```

The fallback may be None even when rule values cannot be None. To compose
mappers of the same result type, place overrides before another mapper's
`rules`. Rules and defaults are validated at construction; evaluating a record
does not validate it as a model.

## Query the collected values

`query()` uses pandas expressions on the current columns, with the Python engine.
Use only trusted expressions. Subclasses can extend `_query_namespace` with
constants or query functions; existing column names take precedence.
For a plain DataFrame, {func}`tollan.utils.pandas.query` provides the same
helpers and accepts additional names through `namespace`.

Use `contains(column, value)` for exact element membership in list, tuple, set,
frozenset or NumPy array cells. Empty and missing collections return false;
other cell types raise `TypeError`. Strings are not treated as collections of
characters, and membership does not perform substring or regex matching.
Pandas `in` and `isin` compare whole cells rather than searching within each
collection.

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
