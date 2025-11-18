"""Time field validators and types."""

from __future__ import annotations

import dataclasses
import numbers
from functools import cached_property
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from astropy.time import Time

from .pydantic import GenerateJsonSchema
from .validator import _SimpleTypeValidatorMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "IsoTimeField",
    "TimeField",
    "TimeValidator",
    "UnixTimeField",
    "time_field",
]


@dataclasses.dataclass(frozen=True)
class TimeValidator(_SimpleTypeValidatorMixin[Time]):
    """Validator for astropy.time.Time with format constraints.

    Parameters
    ----------
    formats_allowed : None | str | Sequence[str], optional
        Allowed time formats (e.g., 'isot', 'unix', 'fits')

    Examples
    --------
    >>> from pydantic import BaseModel
    >>> IsoTime = Annotated[Time, TimeValidator(formats_allowed=['isot', 'fits'])]
    >>> class MyModel(BaseModel):
    ...     timestamp: IsoTime
    >>> model = MyModel(timestamp="2020-01-01T00:00:00")
    >>> model.timestamp.format
    'isot'
    """

    formats_allowed: None | str | Sequence[str] = None

    _field_type: ClassVar = Time
    _field_type_name: ClassVar = "Time"
    _field_type_error_message: ClassVar = (
        "Time or datetime string is required, got {type}."
    )
    _field_value_types: ClassVar = {numbers.Number, str}

    @cached_property
    def _field_formats(self) -> None | tuple[str, ...]:
        """Get normalized time formats."""
        fmts = self.formats_allowed
        if not fmts:
            return None
        if isinstance(fmts, str):
            return (fmts,)
        return tuple(fmts)

    @cached_property
    def _field_value_json_schema_stub(self) -> dict[str, Any]:  # type: ignore[override]
        """JSON schema stub for Time."""
        schema: dict[str, Any] = {
            "type": "string",
            "format": "date-time",
        }
        fmts = self._field_formats
        if fmts is not None:
            schema["time_formats_allowed"] = fmts
        return schema

    @cached_property
    def _field_value_error_message(self) -> str:  # type: ignore[override]
        if self._field_formats is None:
            return "Invalid time format: {value}"
        return f"Time formats {self._field_formats} required, got {{value}}"

    def _field_serialize(self, value: Time) -> str:
        """Serialize Time to ISO format."""
        assert isinstance(value.isot, str)
        return value.isot

    def _field_construct_value(
        self,
        value: str | numbers.Number,
        *args,
        **kwargs,
    ) -> Time:
        """Construct astropy.time.Time."""
        formats = self._field_formats
        if not formats:
            return super()._field_construct_value(value, *args, **kwargs)
        for format in formats:
            try:
                result = super()._field_construct_value(
                    value,
                    *args,
                    field_construct_kw={"format": format},
                )
            except ValueError:
                continue
            else:
                break
        else:
            msg = f"{value!r} does not have the required time formats {formats}."
            raise ValueError(msg)
        return result


_default_time_validator = TimeValidator()
type TimeField = Annotated[Time, _default_time_validator]
type IsoTimeField = Annotated[
    Time,
    TimeValidator(formats_allowed=["isot", "fits", "iso"]),
]
type UnixTimeField = Annotated[
    Time,
    TimeValidator(formats_allowed=("unix", "unix_tai")),
]


def time_field(formats_allowed: str | Sequence[str] | None = None) -> type[Time]:
    """Create a pydantic field type for validating astropy Time.

    Parameters
    ----------
    formats_allowed : None | str | Sequence[str], optional
        Allowed time formats

    Returns
    -------
    Annotated[Time, TimeValidator]
        Pydantic-compatible time field

    Examples
    --------
    >>> UnixTime = time_field(formats_allowed=['unix', 'unix_tai'])
    """
    return Annotated[  # type: ignore[return-value]
        Time,
        TimeValidator(formats_allowed=formats_allowed),
    ]


GenerateJsonSchema.register_default_serializers(
    Time,
    _default_time_validator._field_serialize,
)
