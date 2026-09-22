"""Pydantic annotation for scalar Astropy sky coordinates."""

from __future__ import annotations

from typing import Annotated, Any

import astropy.units as u
from astropy.coordinates import SkyCoord
from pydantic import (
    Field,
    PlainSerializer,
    PlainValidator,
    ValidationInfo,
    WithJsonSchema,
)
from pydantic_core import PydanticCustomError

__all__ = ["SkyCoordField"]

_SOURCE_NAME_META_KEY = "tollan.source_name"
_SKYCOORD_SCHEMA = {
    "type": "string",
    "format": "sky-coordinate",
    "examples": ["M31", "10.6847083d 41.26875d"],
    "x-tollan-coordinate-frame": "icrs",
    "x-tollan-python-type": "astropy.coordinates.SkyCoord",
    "x-tollan-scalar": True,
}


def _parse_coordinate_string(value: str) -> SkyCoord | None:
    try:
        return SkyCoord(value, frame="icrs")
    except (TypeError, ValueError):
        pass
    try:
        # Preserve the established interpretation of unitless pairs as ICRS
        # longitude and latitude in degrees.
        return SkyCoord(value, unit=(u.deg, u.deg), frame="icrs")
    except (TypeError, ValueError):
        return None


def _resolve_coordinate_name(value: str, info: ValidationInfo) -> SkyCoord:
    resolver = SkyCoord.from_name
    if info.context is not None:
        resolver = info.context.get("skycoord_name_resolver", resolver)
    if not callable(resolver):
        error = PydanticCustomError(
            "skycoord_resolver_type",
            "Validation context skycoord_name_resolver should be callable",
        )
        raise error
    try:
        resolved = resolver(value)
    # Resolver implementations are an extension boundary and Astropy does not
    # document a public exception type for ``SkyCoord.from_name``.
    except Exception as e:
        error = PydanticCustomError(
            "skycoord_name_resolution",
            "Could not resolve sky-coordinate name {name}",
            {"name": value},
        )
        raise error from e
    if not isinstance(resolved, SkyCoord):
        error = PydanticCustomError(
            "skycoord_resolver_result",
            "Sky-coordinate name resolver should return an Astropy SkyCoord",
        )
        raise error

    # Do not mutate a coordinate owned by a custom resolver. SkyCoord.info.meta
    # is Astropy's public metadata facility and lets serialization retain the
    # user-facing name without adding private attributes to Astropy objects.
    coord = resolved.copy()
    # ``meta`` may be None or any Mapping, not necessarily a mutable dict.
    # Replacement is therefore safer than assuming ``.update()`` is available.
    metadata = dict(coord.info.meta or {})
    metadata[_SOURCE_NAME_META_KEY] = value
    coord.info.meta = metadata
    return coord


def _validate_skycoord(value: Any, info: ValidationInfo) -> SkyCoord:
    """Parse explicit coordinates first, then resolve source names."""
    if isinstance(value, SkyCoord):
        coord = value
    elif isinstance(value, str):
        coord = _parse_coordinate_string(value)
        if coord is None:
            coord = _resolve_coordinate_name(value, info)
    else:
        error = PydanticCustomError(
            "skycoord_type",
            "Input should be an Astropy SkyCoord or coordinate/name string",
        )
        raise error

    if not coord.isscalar:
        error = PydanticCustomError(
            "skycoord_scalar",
            "SkyCoord should be scalar, got shape {shape}",
            {"shape": str(coord.shape)},
        )
        raise error
    return coord


def _serialize_skycoord(value: SkyCoord) -> str:
    """Retain resolved names; otherwise emit explicit parseable ICRS degrees."""
    # Reading ``SkyCoord.info`` creates a cached attribute. Inspect an already
    # present info object so serializing caller-owned coordinates is mutation-free.
    info = vars(value).get("info")
    metadata = {} if info is None else info.meta or {}
    source_name = metadata.get(_SOURCE_NAME_META_KEY)
    if isinstance(source_name, str):
        return source_name
    icrs = value.icrs
    ra = icrs.ra.to_value(u.deg)
    dec = icrs.dec.to_value(u.deg)
    # Seventeen significant digits round-trip binary64 coordinate values.
    return f"{ra:.17g}d {dec:.17g}d"


type SkyCoordField = Annotated[
    SkyCoord,
    PlainValidator(_validate_skycoord, json_schema_input_type=str),
    PlainSerializer(_serialize_skycoord, return_type=str),
    WithJsonSchema(_SKYCOORD_SCHEMA, mode="serialization"),
    Field(json_schema_extra=_SKYCOORD_SCHEMA),
]
