"""Pydantic annotations for scalar Astropy quantities."""

from __future__ import annotations

import numbers
from functools import lru_cache, partial
from typing import TYPE_CHECKING, Annotated, Any, get_args

import astropy.units as u
from astropy.units import Quantity, get_physical_type
from pydantic import Field, PlainSerializer, PlainValidator, WithJsonSchema
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import TypeForm

__all__ = [
    "AngleQuantityField",
    "DimensionlessQuantityField",
    "FrequencyQuantityField",
    "LengthQuantityField",
    "QuantityField",
    "TimeQuantityField",
    "get_physical_type_from_quantity_type",
    "quantity_field",
]

_QUANTITY_INPUT_TYPE = str | int | float
_QUANTITY_SCHEMA_BASE: dict[str, Any] = {
    "x-tollan-python-type": "astropy.units.Quantity",
    "x-tollan-scalar": True,
}


def _normalize_physical_types(
    physical_types: str | Sequence[str] | None,
) -> tuple[u.PhysicalType, ...]:
    if physical_types is None:
        return ()
    values = (physical_types,) if isinstance(physical_types, str) else physical_types
    try:
        return tuple(_resolve_physical_type(value) for value in values)
    except (TypeError, ValueError) as e:
        msg = f"Unknown physical type in {tuple(values)!r}"
        raise ValueError(msg) from e


def _validate_quantity(
    value: Any,
    *,
    physical_types: tuple[u.PhysicalType, ...] = (),
) -> Quantity:
    """Parse a scalar quantity and enforce optional physical types."""
    if isinstance(value, Quantity):
        quantity = value
    elif isinstance(value, str) or (
        isinstance(value, numbers.Real) and not isinstance(value, bool)
    ):
        try:
            quantity = Quantity(value)
        except (TypeError, ValueError) as e:
            error = PydanticCustomError(
                "quantity_parsing",
                "Input should be a valid scalar quantity",
            )
            raise error from e
    else:
        error = PydanticCustomError(
            "quantity_type",
            "Input should be an Astropy Quantity, string, or real number",
        )
        raise error

    if quantity.shape != ():
        error = PydanticCustomError(
            "quantity_scalar",
            "Quantity should be scalar, got shape {shape}",
            {"shape": str(quantity.shape)},
        )
        raise error

    if not physical_types:
        return quantity
    try:
        actual_type = get_physical_type(quantity.unit)
    except ValueError as e:
        error = PydanticCustomError(
            "quantity_physical_type",
            "Cannot determine the quantity physical type",
        )
        raise error from e
    if actual_type not in physical_types:
        error = PydanticCustomError(
            "quantity_physical_type",
            "Quantity should have physical type {expected}, got {actual}",
            {
                "expected": ", ".join(str(item) for item in physical_types),
                "actual": str(actual_type),
            },
        )
        raise error
    return quantity


def _serialize_quantity(value: Quantity) -> str:
    """Use Astropy's parseable generic quantity syntax."""
    return value.to_string()


_QUANTITY_SERIALIZER = PlainSerializer(_serialize_quantity, return_type=str)


@lru_cache(maxsize=128)
def _resolve_physical_type(value: str) -> u.PhysicalType:
    return get_physical_type(value)


@lru_cache(maxsize=128)
def _quantity_metadata(
    physical_types: tuple[u.PhysicalType, ...],
) -> tuple[Any, ...]:
    schema_extra = dict(_QUANTITY_SCHEMA_BASE)
    if physical_types:
        schema_extra["x-tollan-physical-types"] = [str(item) for item in physical_types]
    serialization_schema = {
        "type": "string",
        "format": "quantity",
        "examples": ["5.0 m"],
        **schema_extra,
    }
    validator = partial(_validate_quantity, physical_types=physical_types)
    return (
        PlainValidator(validator, json_schema_input_type=_QUANTITY_INPUT_TYPE),
        _QUANTITY_SERIALIZER,
        WithJsonSchema(serialization_schema, mode="serialization"),
        Field(json_schema_extra=schema_extra),
        *physical_types,
    )


_QUANTITY_METADATA = _quantity_metadata(())
_LENGTH_METADATA = _quantity_metadata((_resolve_physical_type("length"),))
_ANGLE_METADATA = _quantity_metadata((_resolve_physical_type("angle"),))
_FREQUENCY_METADATA = _quantity_metadata((_resolve_physical_type("frequency"),))
_TIME_METADATA = _quantity_metadata((_resolve_physical_type("time"),))
_DIMENSIONLESS_METADATA = _quantity_metadata((_resolve_physical_type("dimensionless"),))

type QuantityField = Annotated[Quantity, *_QUANTITY_METADATA]
type LengthQuantityField = Annotated[Quantity, *_LENGTH_METADATA]
type AngleQuantityField = Annotated[Quantity, *_ANGLE_METADATA]
type FrequencyQuantityField = Annotated[Quantity, *_FREQUENCY_METADATA]
type TimeQuantityField = Annotated[Quantity, *_TIME_METADATA]
type DimensionlessQuantityField = Annotated[Quantity, *_DIMENSIONLESS_METADATA]


def quantity_field(
    physical_types_allowed: str | Sequence[str] | None = None,
) -> TypeForm[Quantity]:
    """Build a reusable scalar Quantity annotation.

    Parameters
    ----------
    physical_types_allowed : str or sequence of str, optional
        Astropy physical types to accept, such as ``"length"`` or ``"speed"``.
        None accepts any physical type. Numbers represent dimensionless values;
        strings and existing scalar Quantities retain their units.

    Returns
    -------
    typing_extensions.TypeForm
        Pydantic annotation that validates a scalar Quantity and serializes it
        as a value-and-unit string. Arrays and booleans are rejected.

    Raises
    ------
    ValueError
        An allowed physical type is unknown to Astropy.
    """
    physical_types = _normalize_physical_types(physical_types_allowed)
    return Annotated[Quantity, *_quantity_metadata(physical_types)]


def get_physical_type_from_quantity_type(cls: Any) -> u.PhysicalType | None:
    """Return the single physical-type constraint carried by an annotation.

    Parameters
    ----------
    cls : object
        Quantity annotation, including a named alias or Annotated metadata.

    Returns
    -------
    astropy.units.PhysicalType or None
        The sole physical-type constraint, or None if there are zero or multiple
        distinct constraints.
    """
    pending = [cls]
    seen: set[int] = set()
    physical_types: set[u.PhysicalType] = set()
    while pending:
        arg = pending.pop()
        if id(arg) in seen:
            continue
        seen.add(id(arg))
        if isinstance(arg, u.PhysicalType):
            physical_types.add(arg)
        elif isinstance(arg, u.UnitBase):
            physical_types.add(arg.physical_type)
        pending.extend(get_args(arg))
        alias_value = getattr(arg, "__value__", None)
        if alias_value is not None:
            pending.append(alias_value)
    if len(physical_types) == 1:
        return physical_types.pop()
    return None
