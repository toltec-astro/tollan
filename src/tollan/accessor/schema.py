"""Schema definitions for accessor framework."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, NamedTuple, Self

from pydantic import field_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from collections.abc import Mapping as MappingABC
    from collections.abc import Sequence

__all__ = [
    "MISSING",
    "FieldLocation",
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


class FieldLocation(StrEnum):
    """Storage namespace containing a field.

    ``var`` includes array variables, coordinates, and table columns. ``attr``
    selects source attributes; ``dim`` selects dimension lengths.
    """

    attr = auto()
    var = auto()
    dim = auto()


class MappedFieldSource(StrEnum):
    """Field availability when the mapper was resolved."""

    data_source = auto()  # Field found and resolved from data source
    default = auto()  # Field not found, fallback available
    missing = auto()  # Field not found and no default value


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


class _Candidate(NamedTuple):
    """A physical field name and its optional storage location."""

    name: str
    location: FieldLocation | None


@pydantic_dataclass(frozen=True)
class NameMapping(Mapping):
    """Resolve a semantic field from ordered names and storage locations.

    Parameters
    ----------
    candidates : str or sequence
        One name, a sequence of names, or a sequence of (name, location) pairs.
        A name without a location must occur in exactly one supported namespace.
        Candidates are tried in order; an ambiguous name raises ValueError.
    resolve_value : bool, default False
        Whether to capture the value as part of the concrete mapper resolution.
        Values not captured remain ``MISSING`` in the mapper and are read from
        an explicitly supplied data source when requested.

    Examples
    --------
    >>> NameMapping('field').names
    ('field',)

    >>> NameMapping('field', resolve_value=True).resolve_value
    True

    >>> NameMapping.dim(('sample', 'time')).names
    ('sample', 'time')
    >>> NameMapping([
    ...     ('sample', FieldLocation.dim), ('count', FieldLocation.attr)
    ... ]).names
    ('sample', 'count')
    """

    candidates: tuple[_Candidate, ...]
    resolve_value: bool = False

    if TYPE_CHECKING:

        def __init__(
            self,
            candidates: str
            | Sequence[str]
            | Sequence[tuple[str, FieldLocation | None]],
            *,
            resolve_value: bool = False,
        ) -> None: ...

    @field_validator("candidates", mode="before")
    @classmethod
    def normalize_candidates(cls, v: Any) -> Any:
        """Normalize bare names to name/location pairs."""
        if isinstance(v, str):
            v = (v,)
        if not isinstance(v, (list, tuple)):
            # Pydantic v2 does not wrap validator TypeError in ValidationError.
            error = PydanticCustomError(
                "mapping_candidates_type",
                "Input should be a name or a sequence of names or "
                "(name, location) pairs",
            )
            raise error
        if not v:
            msg = "candidates must contain at least one physical field name"
            raise ValueError(msg)
        if any(isinstance(item, FieldLocation) for item in v):
            msg = "Use a sequence of (name, location) pairs or a NameMapping factory"
            raise ValueError(msg)
        if any(not isinstance(item, (str, list, tuple)) for item in v):
            msg = "Candidates must be names or (name, location) pairs"
            raise ValueError(msg)
        return tuple((item, None) if isinstance(item, str) else item for item in v)

    @field_validator("candidates")
    @classmethod
    def validate_candidates(
        cls, candidates: tuple[_Candidate, ...]
    ) -> tuple[_Candidate, ...]:
        """Reject duplicate name/location pairs."""
        if len(set(candidates)) != len(candidates):
            msg = f"candidates must be unique, got {candidates!r}"
            raise ValueError(msg)
        return candidates

    @property
    def names(self) -> tuple[str, ...]:
        """Physical names in candidate order, including cross-location repeats."""
        return tuple(candidate.name for candidate in self.candidates)

    @classmethod
    def _with_location(
        cls,
        names: str | Sequence[str],
        location: FieldLocation,
        *,
        resolve_value: bool,
    ) -> Self:
        names = (names,) if isinstance(names, str) else names
        return cls([(name, location) for name in names], resolve_value=resolve_value)

    @classmethod
    def attr(cls, names: str | Sequence[str], *, resolve_value: bool = False) -> Self:
        """Try one or more names in source attributes, in declaration order."""
        return cls._with_location(
            names, FieldLocation.attr, resolve_value=resolve_value
        )

    @classmethod
    def var(cls, names: str | Sequence[str], *, resolve_value: bool = False) -> Self:
        """Try one or more variable/coordinate/column names in declaration order."""
        return cls._with_location(names, FieldLocation.var, resolve_value=resolve_value)

    @classmethod
    def dim(cls, names: str | Sequence[str], *, resolve_value: bool = False) -> Self:
        """Try one or more dimension names in declaration order."""
        return cls._with_location(names, FieldLocation.dim, resolve_value=resolve_value)

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
    location : FieldLocation or None
        Selected storage namespace. None for an unlocated default or missing field.
    value : Any
        Source value or fallback captured with ``resolve_value=True``, or
        ``MISSING`` when no value was captured.
    value_default : Any
        Configured fallback, retained even if the field exists in the source.
        ``MISSING`` means no fallback was supplied.
    source : MappedFieldSource
        Whether the original resolution found a source field, a default, or neither.
    schema_path : str, optional
        Dot-separated path in the schema.
    """

    mapping: Mapping
    mapping_resolved: NameMapping
    name: str
    location: FieldLocation | None = None
    value: Any = MISSING
    value_default: Any = MISSING
    source: MappedFieldSource = MappedFieldSource.data_source
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
