"""Pydantic annotations for Astropy units and physical types."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

import astropy.units as u
from astropy.units import UnitBase
from pydantic import PlainSerializer, PlainValidator

if TYPE_CHECKING:
    from typing_extensions import TypeForm

__all__ = ["AngleUnitField", "PhysicalTypeField", "UnitField", "unit_field"]


def _parse_unit(value: Any, *, physical_type: u.PhysicalType | None = None) -> UnitBase:
    try:
        unit = u.Unit(value)
    except (TypeError, ValueError) as exc:
        msg = f"Invalid unit: {value!r}"
        raise ValueError(msg) from exc
    if physical_type is not None and unit.physical_type != physical_type:
        msg = f"Unit {unit!s} does not have physical type {physical_type!s}"
        raise ValueError(msg)
    return unit


def _parse_physical_type(value: Any) -> u.PhysicalType:
    try:
        return u.get_physical_type(value)
    except (TypeError, ValueError) as exc:
        msg = f"Invalid physical type: {value!r}"
        raise ValueError(msg) from exc


def _physical_type_name(value: u.PhysicalType) -> str:
    # str(value) joins aliases with '/', which Astropy cannot parse as a name.
    name = next(iter(value))
    if name == "unknown":
        msg = "A physical type without a registered name cannot be serialized"
        raise ValueError(msg)
    return name


def _unit_metadata(physical_type: u.PhysicalType | None) -> tuple[Any, ...]:
    return (
        PlainValidator(
            partial(_parse_unit, physical_type=physical_type),
            json_schema_input_type=str,
        ),
        PlainSerializer(str, return_type=str, when_used="json"),
    )


_UNIT_METADATA = _unit_metadata(None)
_ANGLE_UNIT_METADATA = _unit_metadata(u.get_physical_type("angle"))

type UnitField = Annotated[UnitBase, *_UNIT_METADATA]
"""An Astropy unit, accepting Unit inputs and using unit text in JSON dumps."""

type AngleUnitField = Annotated[UnitBase, *_ANGLE_UNIT_METADATA]
"""An angular Astropy unit, using unit text in JSON dumps."""

type PhysicalTypeField = Annotated[
    u.PhysicalType,
    PlainValidator(_parse_physical_type, json_schema_input_type=str),
    PlainSerializer(_physical_type_name, return_type=str, when_used="json"),
]
"""An Astropy physical type, using one of its names in JSON dumps.

Accepts inputs supported by astropy.units.get_physical_type. Python dumps retain
the PhysicalType object. JSON serialization requires a registered physical-type
name; unnamed physical types raise a serialization error.
"""


def unit_field(physical_type: str | None = None) -> TypeForm[UnitBase]:
    """Build a unit annotation constrained to a physical type.

    Parameters
    ----------
    physical_type : str, optional
        Astropy physical-type name, such as ``"angle"`` or ``"speed"``.
        None accepts any physical type.

    Returns
    -------
    typing_extensions.TypeForm
        Pydantic annotation accepting unit text or Astropy units. Python dumps
        retain the unit object; JSON dumps contain unit text.

    Raises
    ------
    ValueError
        The physical-type name is unknown to Astropy.

    Examples
    --------
    >>> from pydantic import TypeAdapter
    >>> TypeAdapter(unit_field("speed")).validate_python("km/s") == u.km / u.s
    True
    """
    constraint = None if physical_type is None else u.get_physical_type(physical_type)
    return Annotated[UnitBase, *_unit_metadata(constraint)]
