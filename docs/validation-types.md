# Scientific value types

Use annotations from `tollan.config.types` on Pydantic model fields. Validation
returns Python objects such as `Path`, Astropy `Quantity`, `Time`, and `SkyCoord`;
JSON serialization produces strings or numbers suitable for configuration files.

| Validate | Start with | Python result |
| --- | --- | --- |
| Local paths and remote locations | `AnyPath`, `FileLocField` | `Path`, `FileLoc` |
| Values with units | `QuantityField`, physical-type aliases | Astropy `Quantity` |
| Unit and physical-type declarations | `UnitField`, `PhysicalTypeField` | Astropy unit, `PhysicalType` |
| Dates and timestamps | `IsoTimeField`, `UnixTimeField` | Astropy `Time` |
| Coordinates and object names | `SkyCoordField` | Astropy `SkyCoord` |

```{testcode}
from pathlib import Path

from pydantic import BaseModel
from tollan.config.types import AnyPath, IsoTimeField, LengthQuantityField, SkyCoordField


class Observation(BaseModel):
    path: AnyPath
    wavelength: LengthQuantityField
    start: IsoTimeField
    target: SkyCoordField


observation = Observation.model_validate(
    {
        "path": "observation.nc",
        "wavelength": "1.1 mm",
        "start": "2026-01-01T00:00:00",
        "target": "10.6847083d 41.26875d",
    },
    context={"root_path": Path("/data")},
)
assert observation.path == Path("/data/observation.nc")
assert observation.wavelength.to_value("mm") == 1.1
assert observation.start.isot == "2026-01-01T00:00:00.000"
assert isinstance(observation.model_dump(mode="json")["wavelength"], str)
```

Quantity, time, and coordinate fields accept scalar values only. Invalid inputs
raise `pydantic.ValidationError`. The validation and serialization JSON schemas
describe the respective input and output forms:

```{testcode}
validation_schema = Observation.model_json_schema(mode="validation")
serialization_schema = Observation.model_json_schema(mode="serialization")
assert validation_schema["required"] == ["path", "wavelength", "start", "target"]
```

## Paths and file locations

| Annotation | Result and checks |
| --- | --- |
| `AnyPath` | A `Path`; relative paths use `context["root_path"]` when supplied. No existence check. |
| `AbsAnyPath` | Expands `~` and resolves to an absolute path. No existence check. |
| `AbsFilePath` | Requires an existing file and returns its absolute path. |
| `AbsDirectoryPath` | Requires an existing directory and returns its absolute path. |
| `SubPath` | A relative descendant `PurePosixPath`, with no root or `..` component. No filesystem checks or context-root application. |
| `SubPathOrRoot` | Like `SubPath`, but also accepts `.` for the containing directory. Empty paths normalize to `.`. |
| `FileLocField` | A `FileLoc` for local paths or remote URLs, using `root_path` as the local parent unless an explicit parent is supplied. |

Without `root_path`, relative paths use the working directory.
For `FileLocField`, an explicit `local_parent_path`, including `None`, takes
precedence. Existing `FileLoc` objects retain their parent settings. See
[configuration loading](configuration.md#include-configuration-files) for the
difference between included file paths and paths inside settings.

Use `path_field(path_type=..., exists=..., resolve=...)` with `TypeAdapter` for
custom checks. `path_type="file"` and `"dir"` always require an existing object
of that kind; `"new"` requires a nonexistent path with an existing parent.
`exists` controls only the unconstrained `path_type=None` case.

Use `SubPath` for a location to be joined beneath a root later. It accepts nested
paths, but rejects the root itself (`""` or `"."`), absolute paths, and parent
traversal. Paths use `/` separators; redundant separators and `.` components are
removed. It does not expand `~` or resolve symlinks.
Use `SubPathOrRoot` when the containing directory itself is also an allowed
location; `""`, `"."`, and `"./"` all normalize to `PurePosixPath(".")`.

```{testcode}
from pathlib import Path, PurePosixPath
from tollan.config import FrozenBaseModel
from tollan.config.types import SubPath, SubPathOrRoot

class StoreSettings(FrozenBaseModel):
    subpath: SubPath

settings = StoreSettings(subpath="./toltec//tcs/")
assert settings.subpath == PurePosixPath("toltec/tcs")
assert Path("/data_lmt") / settings.subpath == Path("/data_lmt/toltec/tcs")

class SearchSettings(FrozenBaseModel):
    subpaths: tuple[SubPathOrRoot, ...]

search = SearchSettings(subpaths=(".", "tel"))
assert search.subpaths == (PurePosixPath("."), PurePosixPath("tel"))
```

## Quantities

| Need | Annotation |
| --- | --- |
| Any scalar quantity | `QuantityField` |
| Length, angle, frequency, or time | `LengthQuantityField`, `AngleQuantityField`, `FrequencyQuantityField`, `TimeQuantityField` |
| A dimensionless value | `DimensionlessQuantityField` |
| Other physical types or several allowed types | `quantity_field(...)` |

- Accepts a scalar `Quantity`, a unit-bearing string, or a real number (dimensionless).
- Rejects booleans and arrays.
- Restricts physical type without forcing an output unit.
- Serializes the value and unit as a string.

```{testcode}
from pydantic import TypeAdapter
from tollan.config.types import quantity_field

speed = TypeAdapter(quantity_field("speed")).validate_python("12 km/s")
assert speed.to_value("m/s") == 12000
```

`quantity_field()` accepts one physical type, a sequence of allowed physical
types, or `None` for no restriction. Names follow Astropy's physical-type registry.

(unit-declarations)=
### Unit declarations

Use `UnitField` and `PhysicalTypeField` when specifying how to represent a
quantity, without supplying a quantity value. They accept Astropy objects or
text such as `"Hz"` and `"frequency"`. Python dumps retain the objects; JSON
dumps contain unit text and a physical-type name. Compatibility between two
fields is a separate constraint on the containing model.

Use `AngleUnitField` to require angular units, or `unit_field("speed")` for
another physical type. These annotations reject incompatible units without
converting compatible ones to a particular unit.

```{testcode}
from tollan.config.types import PhysicalTypeField, UnitField

class Representation(BaseModel):
    unit: UnitField
    physical_type: PhysicalTypeField

representation = Representation(unit="km/s", physical_type="speed")
assert Representation.model_validate_json(representation.model_dump_json()) == representation
```

## Times

| Input format | Annotation | Formats tried, in order |
| --- | --- | --- |
| Existing scalar `Time` or an inferable format | `TimeField` | Astropy inference |
| ISO date/time string | `IsoTimeField` | `isot`, `fits`, `iso` |
| Unix timestamp | `UnixTimeField` | `unix`, `unix_tai` |
| Explicit format, such as modified Julian date | `time_field("mjd")` | Supplied format(s) |

```{testcode}
from tollan.config.types import UnixTimeField, time_field

epoch = TypeAdapter(UnixTimeField).validate_python(0)
assert epoch.unix == 0
mjd = TypeAdapter(time_field("mjd"))
assert mjd.validate_python(51544.0).mjd == 51544.0
```

- Supply a format for numeric timestamps.
- With multiple formats, parsing tries each in order; serialization uses the first.
- The default serialization format is `isot`; string formats are emitted in UTC.
- ISO serialization retains nanosecond precision regardless of display precision
  or abbreviated display formats. Serialization leaves the input object unchanged.
- Existing `Time` objects preserve their represented instant.
- Use formats that serialize to a scalar JSON string or number.

## Coordinates

| Input | Validation | JSON output |
| --- | --- | --- |
| Scalar `SkyCoord` | Uses the supplied coordinate | ICRS longitude and latitude in degrees |
| Coordinate string, e.g. `"10.6847083d 41.26875d"` | Parses coordinates locally | ICRS longitude and latitude in degrees |
| Unitless pair, e.g. `"10.6847083 41.26875"` | Interprets ICRS degrees | Explicit ICRS degrees |
| Object name, e.g. `"M31"` | Calls `SkyCoord.from_name`; may access the network | Retains the source name |

The default resolver uses Astropy's [CDS/Sesame name-resolution service](https://docs.astropy.org/en/stable/api/astropy.coordinates.SkyCoord.html#astropy.coordinates.SkyCoord.from_name).
Astroquery is not required. To use a catalog of your own, pass a callable returning
a scalar `SkyCoord` through validation context:

```{testcode}
from astropy.coordinates import SkyCoord

catalog = {"M31": SkyCoord("10.6847083d 41.26875d")}
coordinate = TypeAdapter(SkyCoordField).validate_python(
    "M31", context={"skycoord_name_resolver": catalog.__getitem__}
)
assert coordinate.separation(catalog["M31"]).arcsec == 0
```

## Field defaults

`FieldDefaults` exposes declared model defaults through a class attribute.
Annotate the descriptor with its concrete `ClassVar` type:

```{testcode}
from typing import ClassVar
from tollan.config import FrozenBaseModel
from tollan.config.types import FieldDefaults


class Settings(FrozenBaseModel):
    defaults: ClassVar[FieldDefaults] = FieldDefaults()
    retries: int = 3


assert Settings.defaults["retries"] == 3
```

| Field declaration | Lookup result |
| --- | --- |
| Concrete default | Declared value |
| Default factory | Pydantic's undefined sentinel; factory is not called |
| Required field | Pydantic's undefined sentinel |
| Unknown name | Raises `KeyError` |
