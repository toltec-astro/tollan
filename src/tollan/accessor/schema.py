"""Schema definitions for accessor framework."""

from __future__ import annotations

from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any

from pydantic import field_validator
from pydantic.dataclasses import dataclass

__all__ = [
    "MISSING",
    "FieldMapping",
    "MappedField",
    "MappedFieldSource",
    "Mapping",
    "MappingBase",
    "Schema",
]


# Sentinel value for missing/unloaded data
class _MissingSentinel:
    """Sentinel type for missing values."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _MissingSentinel()


class MappedFieldSource(StrEnum):
    """Source of a mapped field's value."""

    DATA_SOURCE = auto()  # Field found and resolved from data source
    DEFAULT = auto()  # Field not found, using default value
    MISSING = auto()  # Field not found and no default value


@dataclass(frozen=True)
class FieldMapping:
    """Configuration for mapping a logical field to physical variable name(s).

    Parameters
    ----------
    names : str or tuple[str, ...]
        Physical variable name(s) to try in order.
    required : bool, default True
        Whether to raise error if field not found.
    resolve_value : bool, default False
        Whether to load value immediately (True) or lazily (False).
    """

    names: tuple[str, ...]
    required: bool = True
    resolve_value: bool = False

    if TYPE_CHECKING:

        def __init__(
            self,
            names: str | tuple[str, ...] | list[str],
            *,
            required: bool = True,
            resolve_value: bool = False,
        ) -> None: ...

    @field_validator("names", mode="before")
    @classmethod
    def validate_names(cls, v: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Normalize names to tuple."""
        # Handle string
        if isinstance(v, str):
            return (v,)
        # Handle list/tuple
        if isinstance(v, (list, tuple)):
            return tuple(v)
        msg = f"names must be str or tuple[str, ...] or list[str], got {type(v)}"
        raise ValueError(msg)


class MappingBase:
    """Base class for field mapping with custom resolution logic.

    Subclass to implement conditional mappings based on data source
    characteristics, context, or previously resolved fields.
    """

    def resolve(
        self,
        context: Any,
    ) -> FieldMapping:
        """Return the FieldMapping to use for this data source.

        Parameters
        ----------
        context : Any
            Mapper instance with data_source and mapped_fields.

        Returns
        -------
        FieldMapping
            Field mapping configuration.
        """
        msg = f"{self.__class__.__name__} must implement resolve()"
        raise NotImplementedError(msg)


class Mapping(FieldMapping, MappingBase):
    """Direct field mapping with no conditional logic.

    Parameters
    ----------
    names : str or tuple[str, ...]
        Physical variable name(s) to try in order.
    required : bool, default True
        Whether to raise error if field not found.
    resolve_value : bool, default False
        Whether to load value immediately.

    Examples
    --------
    >>> Mapping('field')
    Mapping(names=('field',), required=True, resolve_value=False)
    >>> Mapping('field', required=False)
    Mapping(names=('field',), required=False, resolve_value=False)
    >>> Mapping(('field1', 'field2'))
    Mapping(names=('field1', 'field2'), required=True, resolve_value=False)
    """

    def resolve(
        self,
        context: Any,
    ) -> FieldMapping:
        """Return this FieldMapping instance.

        Parameters
        ----------
        context : Any
            Mapper instance.

        Returns
        -------
        FieldMapping
            This instance.
        """
        return self


@dataclass
class MappedField:
    """Result of field resolution.

    Parameters
    ----------
    field_mapping : FieldMapping
        Configuration used for resolution.
    name : str
        Physical field name resolved from data source.
    value : Any
        The loaded value (MISSING if not loaded).
    source : MappedFieldSource
        Where the value came from.
    schema_path : str, optional
        Dot-separated path in the schema.
    """

    field_mapping: FieldMapping
    name: str
    value: Any = MISSING
    source: MappedFieldSource = MappedFieldSource.DATA_SOURCE
    schema_path: str = ""


@dataclass
class Schema:
    """Base class for defining field schemas.

    Examples
    --------
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class MySchema(Schema):
    ...     field1: Mapping = Mapping('physical_name')
    ...     field2: Mapping = Mapping(('alt1', 'alt2'))
    """

    @classmethod
    def get_schema_path(cls, attr_name: str, parent_path: str = "") -> str:
        """Build schema path string for a field.

        Parameters
        ----------
        attr_name : str
            Attribute name.
        parent_path : str, optional
            Parent path for nested schemas.

        Returns
        -------
        str
            Dot-separated schema path.
        """
        if parent_path:
            return f"{parent_path}.{attr_name}"
        return f"{cls.__name__}.{attr_name}"
