"""Pydantic annotations for scalar Astropy times."""

from __future__ import annotations

import numbers
from functools import cache, lru_cache, partial
from typing import TYPE_CHECKING, Annotated, Any, Literal

from astropy.time import Time
from pydantic import Field, PlainSerializer, PlainValidator, WithJsonSchema
from pydantic_core import PydanticCustomError, PydanticSerializationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import TypeForm

__all__ = [
    "IsoTimeField",
    "TimeField",
    "UnixTimeField",
    "time_field",
]

type _TimeValueKind = Literal["string", "number"]
_TIME_INPUT_TYPE = str | int | float
_TIME_SCHEMA_BASE: dict[str, Any] = {
    "x-tollan-python-type": "astropy.time.Time",
    "x-tollan-scalar": True,
}
_FORMAT_PROBE = Time("2020-01-01T00:00:00", format="isot", scale="utc")


def _normalize_formats(
    formats: str | Sequence[str] | None,
) -> tuple[str, ...]:
    if formats is None:
        return ()
    result = (formats,) if isinstance(formats, str) else tuple(formats)
    for time_format in result:
        _time_format_kind(time_format)
    return result


# ``Time.FORMATS`` is finite in a running process, and classification otherwise
# performs a real Astropy conversion. Cache that immutable result.
@cache
def _time_format_kind(time_format: str) -> _TimeValueKind:
    """Classify a format through Astropy's public registry and conversion API."""
    if time_format not in Time.FORMATS:
        msg = f"Unknown Astropy time format {time_format!r}"
        raise ValueError(msg)
    value = _FORMAT_PROBE.to_value(time_format)
    if isinstance(value, str | bytes):
        return "string"
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return "number"
    msg = (
        f"Astropy time format {time_format!r} produces {type(value).__name__}; "
        "Tollan configuration fields require scalar JSON strings or numbers"
    )
    raise ValueError(msg)


def _time_input_type(formats: tuple[str, ...]) -> Any:
    if not formats:
        return _TIME_INPUT_TYPE
    kinds = {_time_format_kind(time_format) for time_format in formats}
    if kinds == {"string"}:
        return str
    if kinds == {"number"}:
        return int | float
    return _TIME_INPUT_TYPE


def _validate_time(value: Any, *, formats: tuple[str, ...]) -> Time:
    """Parse a scalar Astropy time using only explicitly selected formats."""
    if isinstance(value, Time):
        result = value
    elif not (
        isinstance(value, str)
        or (isinstance(value, numbers.Real) and not isinstance(value, bool))
    ):
        error = PydanticCustomError(
            "time_type",
            "Input should be an Astropy Time, string, or real number",
        )
        raise error
    elif not formats:
        try:
            result = Time(value)
        except (TypeError, ValueError) as e:
            error = PydanticCustomError(
                "time_parsing",
                "Input should be a valid scalar Astropy time",
            )
            raise error from e
    else:
        for time_format in formats:
            try:
                result = Time(value, format=time_format)
            except (TypeError, ValueError):
                continue
            break
        else:
            error = PydanticCustomError(
                "time_parsing",
                "Input should use one of the time formats: {formats}",
                {"formats": ", ".join(formats)},
            )
            raise error

    if not result.isscalar:
        error = PydanticCustomError(
            "time_scalar",
            "Time should be scalar, got shape {shape}",
            {"shape": str(result.shape)},
        )
        raise error
    return result


def _serialize_time(value: Time, *, output_format: str) -> str | float:
    """Serialize through Astropy, preserving the represented instant."""
    if _time_format_kind(output_format) == "string":
        # Astropy's scalar string formats do not encode the time scale. Emit
        # UTC so parsing the string back with the same format preserves time.
        # Display precision must not round the serialized fractional seconds.
        output_value = value.utc.replicate()
        output_value.precision = 9
        result = output_value.to_value(output_format)
    else:
        result = value.to_value(output_format)
    if isinstance(result, str):
        return result
    if isinstance(result, bytes):
        return result.decode("ascii")
    if isinstance(result, numbers.Real) and not isinstance(result, bool):
        return float(result)
    msg = (
        f"Astropy time format {output_format!r} did not produce a scalar "
        "JSON string or number"
    )
    raise PydanticSerializationError(msg)


# Reusing identical Pydantic metadata keeps dynamic field factories cheap and
# lets Pydantic reuse the same validator/serializer callables.
@lru_cache(maxsize=128)
def _time_metadata(formats: tuple[str, ...]) -> tuple[Any, ...]:
    output_format = formats[0] if formats else "isot"
    output_kind = _time_format_kind(output_format)
    schema_extra = dict(_TIME_SCHEMA_BASE)
    if formats:
        schema_extra["x-tollan-time-formats"] = list(formats)
    example = _serialize_time(_FORMAT_PROBE, output_format=output_format)
    serialization_schema = {
        "type": output_kind,
        "format": "astropy-time",
        "examples": [example],
        "x-tollan-output-format": output_format,
        **schema_extra,
    }
    return (
        PlainValidator(
            partial(_validate_time, formats=formats),
            json_schema_input_type=_time_input_type(formats),
        ),
        PlainSerializer(
            partial(_serialize_time, output_format=output_format),
            return_type=str | float,
        ),
        WithJsonSchema(serialization_schema, mode="serialization"),
        Field(json_schema_extra=schema_extra),
    )


_TIME_METADATA = _time_metadata(())
_ISO_TIME_METADATA = _time_metadata(("isot", "fits", "iso"))
_UNIX_TIME_METADATA = _time_metadata(("unix", "unix_tai"))

type TimeField = Annotated[Time, *_TIME_METADATA]
type IsoTimeField = Annotated[Time, *_ISO_TIME_METADATA]
type UnixTimeField = Annotated[Time, *_UNIX_TIME_METADATA]


def time_field(
    formats_allowed: str | Sequence[str] | None = None,
) -> TypeForm[Time]:
    """Build a reusable scalar Time annotation from Astropy format names.

    Parameters
    ----------
    formats_allowed : str or sequence of str, optional
        Formats to try in order, such as ``"mjd"`` or ``("isot", "iso")``.
        None delegates format inference to Astropy. Numeric inputs require
        an explicit format. Existing scalar Time objects are accepted directly.

    Returns
    -------
    typing_extensions.TypeForm
        Pydantic annotation producing a scalar Time. Serialization uses the
        first allowed format, or ``isot`` by default. String output uses UTC,
        full subformats, and nine fractional-second digits where supported,
        independently of the input object's display settings.

    Raises
    ------
    ValueError
        A format is unknown or does not produce a scalar JSON string or number.
    """
    formats = _normalize_formats(formats_allowed)
    return Annotated[Time, *_time_metadata(formats)]
