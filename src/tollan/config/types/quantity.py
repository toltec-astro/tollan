"""Quantity field validators and types."""

from __future__ import annotations

import dataclasses
import numbers
from functools import cached_property
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import astropy.units as u
from astropy.units import Quantity, get_physical_type

from ...utils.typing import get_typing_args
from .pydantic import GenerateJsonSchema
from .validator import _SimpleTypeValidatorMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "AngleQuantityField",
    "DimensionlessQuantityField",
    "FrequencyQuantityField",
    "LengthQuantityField",
    "QuantityField",
    "QuantityValidator",
    "TimeQuantityField",
    "get_physical_type_from_quantity_type",
    "quantity_field",
]


@dataclasses.dataclass(frozen=True)
class QuantityValidator(_SimpleTypeValidatorMixin[Quantity]):
    """Validator for astropy.units.Quantity with physical type constraints.

    Parameters
    ----------
    physical_types_allowed : None | str | Sequence[str], optional
        Allowed physical types (e.g., 'length', 'angle', 'time')

    Examples
    --------
    >>> from pydantic import BaseModel
    >>> Length = Annotated[Quantity, QuantityValidator(physical_types_allowed='length')]
    >>> class MyModel(BaseModel):
    ...     distance: Length
    >>> model = MyModel(distance="5.0 m")
    >>> model.distance
    <Quantity 5. m>
    """

    physical_types_allowed: None | str | Sequence[str] = None

    _field_type: ClassVar = Quantity
    _field_type_name: ClassVar = "Quantity"
    _field_type_error_message: ClassVar = (
        "Quantity, string, or number is required, got {type}."
    )
    _field_value_types: ClassVar = {numbers.Number, str}

    @cached_property
    def _field_physical_types(self) -> None | tuple[str, ...]:
        """Get normalized physical types."""
        if self.physical_types_allowed is None:
            return None
        if isinstance(self.physical_types_allowed, str):
            return (self.physical_types_allowed,)
        return tuple(self.physical_types_allowed)

    @cached_property
    def _field_value_json_schema_stub_impl(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """JSON schema stub for Quantity."""
        schema: dict[str, Any] = {
            "type": "string",
            "format": "quantity",
        }
        types = self._field_physical_types
        if types is not None:
            schema["physical_types_allowed"] = types
        return schema

    @cached_property
    def _field_value_error_message(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Get error message for value validation."""
        if self._field_physical_types is None:
            return "Invalid quantity: {value}"
        return (
            f"Quantity with physical type {self._field_physical_types} "
            f"required, got {{value}}"
        )

    def _field_validate_value(self, value: Quantity, *args, **kwargs) -> Quantity:
        """Validate physical type constraints."""
        value = super()._field_validate_value(value, *args, **kwargs)
        physical_types = self._field_physical_types
        if physical_types is None:
            return value

        try:
            actual_type = get_physical_type(value)
        except ValueError as e:
            msg = f"Cannot determine physical type of {value!r}"
            raise ValueError(
                msg,
            ) from e

        # actual_type._physical_type can be a list or string
        actual_physical = actual_type._physical_type
        if isinstance(actual_physical, str):
            actual_physical = [actual_physical]

        # Check if any of the actual physical types match allowed types
        if not any(pt in physical_types for pt in actual_physical):
            msg = f"Physical type {physical_types} required, got {actual_physical}"
            raise ValueError(msg)

        return value


_default_quantity_validator = QuantityValidator()
type QuantityField = Annotated[Quantity, _default_quantity_validator]
type LengthQuantityField = Annotated[
    Quantity,
    QuantityValidator(physical_types_allowed="length"),
]
type AngleQuantityField = Annotated[
    Quantity,
    QuantityValidator(physical_types_allowed="angle"),
]
type FrequencyQuantityField = Annotated[
    Quantity,
    QuantityValidator(physical_types_allowed="frequency"),
]
type TimeQuantityField = Annotated[
    Quantity,
    QuantityValidator(physical_types_allowed="time"),
]
type DimensionlessQuantityField = Annotated[
    Quantity,
    QuantityValidator(physical_types_allowed="dimensionless"),
]


def quantity_field(
    physical_types_allowed: str | Sequence[str] | None = None,
) -> type[Quantity]:
    """Create a pydantic field type for validating astropy Quantity.

    Parameters
    ----------
    physical_types_allowed : None | str | Sequence[str], optional
        Allowed physical types

    Returns
    -------
    Annotated[Quantity, QuantityValidator]
        Pydantic-compatible quantity field

    Examples
    --------
    >>> Speed = quantity_field(physical_types_allowed='speed')
    """
    return Annotated[  # type: ignore[return-value]
        Quantity,
        QuantityValidator(physical_types_allowed=physical_types_allowed),
    ]


def get_physical_type_from_quantity_type(cls: type) -> u.PhysicalType | None:
    """Extract physical type from a Quantity type alias annotation.

    Parameters
    ----------
    cls : type
        Type to inspect (typically an Annotated Quantity type)

    Returns
    -------
    astropy.units.PhysicalType | None
        Physical type if found, None otherwise

    Examples
    --------
    >>> from typing import Annotated
    >>> Length = Annotated[Quantity, QuantityValidator(physical_types_allowed='length')]
    >>> # Function extracts physical type from the annotation metadata
    >>> get_physical_type_from_quantity_type(Length)  # doctest: +SKIP
    PhysicalType('length')
    """
    # Extract all typing args and check for PhysicalType or UnitBase instances
    args = get_typing_args(cls)

    for arg in args:
        # Check for PhysicalType directly
        if isinstance(arg, u.PhysicalType):
            return arg
        # Check for UnitBase (includes Unit, IrreducibleUnit, etc.)
        if isinstance(arg, u.UnitBase):
            return arg.physical_type

    return None


# Register serializer for Quantity
GenerateJsonSchema.register_default_serializers(
    Quantity,
    _default_quantity_validator._field_serialize,
)
