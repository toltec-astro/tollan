"""Pydantic utilities for configuration types."""

from __future__ import annotations

import dataclasses
import functools
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic.json_schema import GenerateJsonSchema as _GenerateJsonSchema

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

__all__ = [
    "FieldDefaults",
    "GenerateJsonSchema",
]


class GenerateJsonSchema(_GenerateJsonSchema):
    """Custom JSON schema generator with type-specific serializers.

    This extends Pydantic's default JSON schema generation to handle
    custom astronomy types (Time, Quantity, SkyCoord) properly.

    Attributes
    ----------
    _default_serializers : ClassVar[dict[type[Any], Callable]]
        Registry of type-specific serializers

    Examples
    --------
    >>> from tollan.config import FrozenBaseModel
    >>> class MyModel(FrozenBaseModel):
    ...     value: int = 42
    >>> schema = MyModel.model_json_schema()
    >>> 'value' in schema['properties']
    True
    """

    _default_serializers: ClassVar[dict[type[Any], Callable]] = {}

    @classmethod
    def register_default_serializers(
        cls,
        dft_type: type[Any],
        handler: Callable,
    ) -> None:
        """Add handler for type.

        Parameters
        ----------
        dft_type : type[Any]
            Type to register serializer for
        handler : Callable
            Serialization function
        """
        cls._default_serializers[dft_type] = handler

    def encode_default(self, dft: Any) -> Any:
        """Override default behavior to invoke custom type handlers.

        Parameters
        ----------
        dft : Any
            Default value to encode

        Returns
        -------
        Any
            Encoded default value
        """
        for dft_type, handler in self._default_serializers.items():
            if isinstance(dft, dft_type):
                dft = handler(dft)
                break
        return super().encode_default(dft)


@dataclasses.dataclass(frozen=True)
class _FieldDefaultAccessor:
    model_cls: type[BaseModel]

    def __getitem__(self, name: str) -> Any:
        return self.model_cls.model_fields[name].get_default()


@functools.lru_cache
def _get_field_default_accessor(cls: type[BaseModel]) -> _FieldDefaultAccessor:
    return _FieldDefaultAccessor(cls)


class FieldDefaults:
    """Descriptor for accessing model field defaults.

    Provides convenient access to default values of model fields.

    Examples
    --------
    >>> from tollan.config import FrozenBaseModel
    >>> from typing import ClassVar
    >>> class MyModel(FrozenBaseModel):
    ...     defaults: ClassVar = FieldDefaults()
    ...     value: int = 42
    >>> MyModel.defaults['value']
    42
    """

    def __get__(self, obj, cls):
        return _get_field_default_accessor(cls)
