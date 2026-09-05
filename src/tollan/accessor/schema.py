"""Schema definitions for accessor framework."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any

from pydantic import field_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from collections.abc import Mapping as MappingABC

__all__ = [
    "MISSING",
    "MappedField",
    "MappedFieldSource",
    "Mapping",
    "MappingContext",
    "NameMapping",
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


class Mapping:
    """Strategy for resolving one semantic field.

    Subclass this class for conditional mappings. Direct ordered-name
    resolution is provided by :class:`NameMapping`.

    Examples
    --------
    >>> class ConditionalMapping(Mapping):
    ...     def resolve(self, context):
    ...         if context.data_source.attrs.get('version') == 2:
    ...             return NameMapping('field_v2')
    ...         return NameMapping('field_v1')
    """

    def resolve(
        self,
        context: MappingContext,
    ) -> NameMapping:
        """Return the mapping to use for this data source.

        Parameters
        ----------
        context : MappingContext
            Current source, schema, and fields resolved so far.

        Returns
        -------
        NameMapping
            Concrete ordered-name mapping.
        """
        msg = f"{self.__class__.__name__} must implement resolve()"
        raise NotImplementedError(msg)


@pydantic_dataclass(frozen=True)
class NameMapping(Mapping):
    """Resolve a semantic field from ordered physical-name candidates.

    Maps a logical field name to one or more physical variable names in the data source.

    Parameters
    ----------
    names : str or tuple[str, ...]
        Physical variable name(s) to try in order.
    resolve_value : bool, default False
        Whether to capture the value as part of the concrete mapper resolution.
        Values not captured remain ``MISSING`` in the mapper and are read from
        an explicitly supplied data source when requested.

    Examples
    --------
    >>> NameMapping('field')
    NameMapping(names=('field',), resolve_value=False)

    >>> NameMapping('field', resolve_value=True)
    NameMapping(names=('field',), resolve_value=True)

    >>> NameMapping(('field1', 'field2'))
    NameMapping(names=('field1', 'field2'), resolve_value=False)
    """

    names: tuple[str, ...]
    resolve_value: bool = False

    if TYPE_CHECKING:

        def __init__(
            self,
            names: str | tuple[str, ...] | list[str],
            *,
            resolve_value: bool = False,
        ) -> None: ...

    @field_validator("names", mode="before")
    @classmethod
    def validate_names(cls, v: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Normalize names to tuple."""
        if isinstance(v, str):
            names = (v,)
        elif isinstance(v, (list, tuple)):
            names = tuple(v)
        else:
            # Pydantic v2 does not wrap validator TypeError in ValidationError.
            error = PydanticCustomError(
                "mapping_names_type",
                "Input should be a string, tuple of strings, or list of strings",
            )
            raise error
        if not names:
            msg = "names must contain at least one physical field name"
            raise ValueError(msg)
        if all(isinstance(name, str) for name in names) and len(set(names)) != len(
            names,
        ):
            msg = f"names must be unique, got {names!r}"
            raise ValueError(msg)
        return names

    def resolve(
        self,
        context: MappingContext,
    ) -> NameMapping:
        """Return this mapping instance.

        Parameters
        ----------
        context : MappingContext
            Resolution context (unused by a direct name mapping).

        Returns
        -------
        NameMapping
            This instance.
        """
        return self


@dataclass(frozen=True, slots=True)
class MappedField:
    """Result of field resolution.

    Parameters
    ----------
    mapping : Mapping
        Original strategy declared by the schema.
    mapping_resolved : NameMapping
        Concrete name mapping returned by resolution.
    name : str
        Physical field name resolved from data source.
    value : Any
        Value captured during mapper resolution, or ``MISSING`` when the
        mapping does not retain a source value.
    source : MappedFieldSource
        Where the value came from.
    schema_path : str, optional
        Dot-separated path in the schema.
    """

    mapping: Mapping
    mapping_resolved: NameMapping
    name: str
    value: Any = MISSING
    source: MappedFieldSource = MappedFieldSource.DATA_SOURCE
    schema_path: str = ""


@dataclass(frozen=True, slots=True)
class MappingContext:
    """Short-lived state available while resolving mappings."""

    data_source: Any
    schema: Schema
    mapped_fields: MappingABC[Mapping, MappedField]


@dataclass
class Schema:
    """Base class for a flat collection of semantic fields.

    Examples
    --------
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class MySchema(Schema):
    ...     field1: Mapping = NameMapping('physical_name')
    ...     field2: Mapping = NameMapping(('alt1', 'alt2'))
    """

    @classmethod
    def get_schema_path(cls, attr_name: str) -> str:
        """Build schema path string for a field.

        Parameters
        ----------
        attr_name : str
            Attribute name.

        Returns
        -------
        str
            Dot-separated schema path.
        """
        return f"{cls.__name__}.{attr_name}"
