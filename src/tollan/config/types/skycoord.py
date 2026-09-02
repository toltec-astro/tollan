"""SkyCoord field validator and types."""

from __future__ import annotations

import dataclasses
from functools import cached_property
from typing import Annotated, Any, ClassVar

from astropy.coordinates import SkyCoord

from .pydantic import GenerateJsonSchema
from .validator import _SimpleTypeValidatorMixin

__all__ = [
    "SkyCoordField",
    "SkyCoordValidator",
]


@dataclasses.dataclass(frozen=True)
class SkyCoordValidator(_SimpleTypeValidatorMixin[SkyCoord]):
    """Validator for astropy.coordinates.SkyCoord.

    Validates celestial coordinate strings and parses them to SkyCoord objects.
    Supports round-trip serialization by preserving original coordinate names.

    Examples
    --------
    >>> from pydantic import BaseModel
    >>> class Target(BaseModel):
    ...     position: SkyCoordField
    >>> target = Target(position="10.6847083d 41.26875d")
    >>> isinstance(target.position, SkyCoord)
    True
    """

    _field_type: ClassVar = SkyCoord
    _field_type_name: ClassVar = "SkyCoord"
    _field_type_error_message: ClassVar = (
        "SkyCoord or sky coordinate string is required, got {type}."
    )
    _field_value_types: ClassVar = {str}

    _skycoord_name_attr = "_tollan_skycoord_name__"
    """Helps round-trip coordinates by name."""

    @cached_property
    def _field_value_json_schema_stub(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """JSON schema stub for SkyCoord."""
        return {
            "type": "string",
            "format": "sky_coord",
        }

    def _field_serialize(self, value: SkyCoord) -> str:
        """Serialize SkyCoord to string."""
        name_attr = self._skycoord_name_attr
        if hasattr(value, name_attr):
            return getattr(value, name_attr)
        result = value.to_string(style="hmsdms")
        assert isinstance(result, str)
        return result.replace(" ", "")

    @cached_property
    def _field_value_error_message(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Get error message for value validation."""
        return "SkyCoord required, got {value}"

    def _field_construct_value(self, value: str, *args, **kwargs) -> SkyCoord:
        """Construct a SkyCoord from a deterministic coordinate string.

        Name resolution is deliberately excluded: model validation must not
        perform network I/O. Callers that need named objects should resolve
        them explicitly before validation and pass the resulting ``SkyCoord``.
        """
        try:
            try:
                coord = SkyCoord(value, frame="icrs")
            except ValueError:
                # Match the deterministic fallback historically provided by
                # astroquery.parse_coordinates for unitless string pairs.
                coord = SkyCoord(value, unit="deg", frame="icrs")
        except (TypeError, ValueError) as e:
            msg = self._field_value_error_message.format(value=value)
            raise ValueError(msg) from e
        setattr(coord, self._skycoord_name_attr, value)
        return coord


default_skycoord_validator = SkyCoordValidator()
type SkyCoordField = Annotated[SkyCoord, default_skycoord_validator]

GenerateJsonSchema.register_default_serializers(
    SkyCoord,
    default_skycoord_validator._field_serialize,
)
