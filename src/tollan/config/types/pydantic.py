"""Pydantic utilities for configuration types."""

from __future__ import annotations

import dataclasses
import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "FieldDefaults",
]


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
