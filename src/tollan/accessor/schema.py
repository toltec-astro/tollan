"""Define a consistent vocabulary for entities that may occur in data.

Schemas give fields semantic names independent of storage conventions. Mappings
describe how those fields may be represented in data, allowing a mapper to
identify them in a particular source.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum, auto
from inspect import get_annotations
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, NamedTuple, Self

from pydantic import Field, ValidateAs, field_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic_core import PydanticCustomError

from ..config.types import SubPath

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
    "SubpathMapping",
]


# Sentinel value for missing/unloaded data
class _MissingSentinel:
    """Sentinel type for missing values."""

    def __repr__(self) -> str:
        return "MISSING"

    def __reduce__(self) -> str:
        return "MISSING"


MISSING = _MissingSentinel()


class FieldLocation(StrEnum):
    """Kind of data entity represented by a mapping.

    ``var`` includes array variables, coordinates, and table columns. ``attr``
    selects source attributes; ``dim`` selects dimension lengths. ``path``
    selects a subtree by its path.
    """

    attr = auto()
    var = auto()
    dim = auto()
    path = auto()


class MappedFieldSource(StrEnum):
    """Field availability when the mapper was resolved."""

    data_source = auto()  # Field found and resolved from data source
    default = auto()  # Field not found, fallback available
    missing = auto()  # Field not found and no default value


class Mapping:
    """Specify a field mapping for a resolution context.

    Subclasses implement ``resolve`` to return a ``NameMapping`` for the supplied
    context. Use ``NameMapping`` directly for a fixed declaration of candidate
    names, locations, and parent. The mapper selects among those candidates.

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
        """Return the name mapping for the supplied resolution context.

        Parameters
        ----------
        context : MappingContext
            Current source, schema, and fields resolved so far.

        Returns
        -------
        NameMapping
            Candidate names, locations, and parent for this field.
        """
        msg = f"{self.__class__.__name__} must implement resolve()"
        raise NotImplementedError(msg)


class _Candidate[
    NameT: str = str,
    LocationT: FieldLocation | None = FieldLocation | None,
](NamedTuple):
    """A data name or subtree path and its optional location."""

    name: NameT
    location: LocationT


type _SubpathCandidate = _Candidate[
    Annotated[
        str,
        # ValidateAs supports aliases; its annotation still requires type.
        ValidateAs(SubPath, str),  # ty: ignore[invalid-argument-type]
    ],
    Literal[FieldLocation.path],
]


@pydantic_dataclass(frozen=True)
class NameMapping(Mapping):
    """Candidate names, entity kinds, and containing subtree for a schema field.

    Parameters
    ----------
    candidates : str or sequence
        One name, a sequence of names, or a sequence of (name, location) pairs.
        Supply at least one candidate, in preference order; name/location pairs
        must be unique. A name without a location may match at
        most one supported entity kind; ambiguous matches raise ValueError.
    resolve_value : bool, default False
        Whether mapper resolution captures the value in ``MappedField.value``.
        The default leaves that value ``MISSING``. Mapper getters read from
        their supplied data source regardless of this setting.
    parent : NameMapping, optional
        Path mapping for the subtree containing this field. ``None`` denotes
        a field on the mapping context's data source.

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

    >>> output = NameMapping.path(("results", "legacy_results"))
    >>> signal = output / NameMapping.var("signal")
    >>> signal == NameMapping.var("signal", parent=output)
    True
    >>> signal.names
    ('signal',)
    """

    candidates: Annotated[tuple[_Candidate, ...], Field(min_length=1)]
    resolve_value: bool = False
    parent: NameMapping | None = None

    if TYPE_CHECKING:

        def __init__(
            self,
            candidates: str
            | Sequence[str]
            | Sequence[tuple[str, FieldLocation | None]],
            *,
            resolve_value: bool = False,
            parent: NameMapping | None = None,
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

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, parent: NameMapping | None) -> NameMapping | None:
        """Require a parent mapping to identify a subtree."""
        if parent is not None and any(
            candidate.location != FieldLocation.path for candidate in parent.candidates
        ):
            msg = "A mapping parent must contain only path candidates"
            raise ValueError(msg)
        return parent

    def __truediv__[ChildT: NameMapping](self, child: ChildT) -> ChildT:
        """Return a child mapping with this path mapping as its parent.

        Parameters
        ----------
        child : NameMapping
            Declaration for a field within this subtree, with no parent set.

        Returns
        -------
        NameMapping
            Mapping of the same type as ``child``, with this path as its parent.

        Raises
        ------
        ValueError
            This mapping is not a path mapping, or the child already has a parent.
        """
        if not isinstance(child, NameMapping):
            return NotImplemented
        if child.parent is not None:
            msg = "The child mapping already has a parent"
            raise ValueError(msg)
        return replace(child, parent=self)

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
        parent: NameMapping | None = None,
    ) -> Self:
        names = (names,) if isinstance(names, str) else names
        return cls(
            [(name, location) for name in names],
            resolve_value=resolve_value,
            parent=parent,
        )

    @classmethod
    def attr(
        cls,
        names: str | Sequence[str],
        *,
        resolve_value: bool = False,
        parent: NameMapping | None = None,
    ) -> Self:
        """Create an attribute mapping from ordered candidate names.

        Parameters
        ----------
        names : str or sequence of str
            Candidate attribute names within the containing subtree,
            in preference order.
        resolve_value : bool, default False
            Store the selected attribute value in the resolved mapper.
        parent : NameMapping, optional
            Path mapping for the subtree containing the attribute. ``None``
            denotes an attribute on the mapping context's data source.

        Returns
        -------
        NameMapping
            Mapping for the supplied attribute names and parent.

        Raises
        ------
        ValueError
            Candidates are empty or duplicated, or the parent is not a path mapping.
        """
        return cls._with_location(
            names, FieldLocation.attr, resolve_value=resolve_value, parent=parent
        )

    @classmethod
    def var(
        cls,
        names: str | Sequence[str],
        *,
        resolve_value: bool = False,
        parent: NameMapping | None = None,
    ) -> Self:
        """Create a variable mapping from ordered candidate names.

        Parameters
        ----------
        names : str or sequence of str
            Candidate variable, coordinate, or column names within the containing
            subtree, in preference order.
        resolve_value : bool, default False
            Store the selected variable's values in the resolved mapper, loading
            its array data. The default leaves values unloaded.
        parent : NameMapping, optional
            Path mapping for the subtree containing the variable. ``None``
            denotes a variable on the mapping context's data source.

        Returns
        -------
        NameMapping
            Mapping for the supplied variable names and parent.

        Raises
        ------
        ValueError
            Candidates are empty or duplicated, or the parent is not a path mapping.
        """
        return cls._with_location(
            names, FieldLocation.var, resolve_value=resolve_value, parent=parent
        )

    @classmethod
    def dim(
        cls,
        names: str | Sequence[str],
        *,
        resolve_value: bool = False,
        parent: NameMapping | None = None,
    ) -> Self:
        """Create a dimension mapping from ordered candidate names.

        Parameters
        ----------
        names : str or sequence of str
            Candidate dimension names within the containing subtree,
            in preference order.
        resolve_value : bool, default False
            Store the selected dimension size in the resolved mapper.
        parent : NameMapping, optional
            Path mapping for the subtree containing the dimension. ``None``
            denotes a dimension on the mapping context's data source.

        Returns
        -------
        NameMapping
            Mapping for the supplied dimension names and parent.

        Raises
        ------
        ValueError
            Candidates are empty or duplicated, or the parent is not a path mapping.
        """
        return cls._with_location(
            names, FieldLocation.dim, resolve_value=resolve_value, parent=parent
        )

    @classmethod
    def path(
        cls,
        paths: str | Sequence[str],
        *,
        resolve_value: bool = False,
        parent: NameMapping | None = None,
    ) -> Self:
        """Create a subtree mapping from ordered candidate paths.

        Parameters
        ----------
        paths : str or sequence of str
            Candidate paths in preference order. Relative paths are based on
            ``parent``, or on the mapping context's data source for ``parent=None``.
            ``.`` denotes that node; absolute paths are based on the tree root.
        resolve_value : bool, default False
            Capture the native subtree during resolution without loading arrays.
        parent : NameMapping, optional
            Path mapping for the node relative to which the candidate paths are
            defined. ``None`` denotes the mapping context's data source.

        Returns
        -------
        NameMapping
            Mapping with the supplied path candidates in lookup order.

        See Also
        --------
        SubpathMapping : Restrict candidates to relative descendant paths.
        """
        return cls._with_location(
            paths, FieldLocation.path, resolve_value=resolve_value, parent=parent
        )

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


@pydantic_dataclass(frozen=True)
class SubpathMapping(NameMapping):
    """Ordered relative descendant paths within a namespace.

    Parameters
    ----------
    candidates : sequence of (SubPath, FieldLocation.path)
        Candidate subpaths in preference order. Use the ``path`` factory to
        supply the paths without their location tags. See
        :data:`~tollan.config.types.path.SubPath` for accepted path values.
    resolve_value : bool, default False
        Capture the selected subtree during mapper resolution.
    parent : NameMapping, optional
        Path mapping for the node relative to which the candidate paths are
        defined. ``None`` denotes the mapping context's data source.

    Raises
    ------
    ValueError
        A candidate is not a valid subpath, uses another storage location, or
        duplicates a normalized path.

    Examples
    --------
    >>> SubpathMapping.path(("samples", "_input")).names
    ('samples', '_input')
    >>> SubpathMapping.path("diagnostics/spectrum").names
    ('diagnostics/spectrum',)
    """

    candidates: Annotated[tuple[_SubpathCandidate, ...], Field(min_length=1)]


@dataclass(frozen=True, slots=True)
class MappedField:
    """Selected data location and fallback value for one schema declaration.

    Parameters
    ----------
    mapping : Mapping
        Mapping declared by the schema attribute.
    mapping_resolved : NameMapping
        Candidate specification returned by ``mapping.resolve(context)``.
    name : str
        Selected data name or subtree path within ``parent_path``. This is the
        first candidate when none exists in the resolution data source.
    location : FieldLocation or None
        Selected entity kind: attribute, variable, dimension, or subtree.
        ``None`` means no entity kind was identified.
    value : Any
        Source value or fallback captured with ``resolve_value=True``, or
        ``MISSING`` when no value was captured.
    value_default : Any
        Configured fallback, retained even if the field exists in the source.
        ``MISSING`` means no fallback was supplied.
    source : MappedFieldSource
        Whether the original resolution found a source field, a default, or neither.
    schema_path : str, optional
        Diagnostic identifier ``SchemaClass.attribute``, not a data-tree path.
    parent_path : str, optional
        Selected path of the containing subtree. Relative paths are based on
        the mapping context's data source. ``None`` denotes that data source
        itself. Access methods apply this path to their supplied data source.
    """

    mapping: Mapping
    mapping_resolved: NameMapping
    name: str
    location: FieldLocation | None = None
    value: Any = MISSING
    value_default: Any = MISSING
    source: MappedFieldSource = MappedFieldSource.data_source
    schema_path: str = ""
    parent_path: str | None = None


@dataclass(frozen=True, slots=True)
class MappingContext:
    """Data source and schema fields available during mapping resolution.

    Parameters
    ----------
    data_source : object or None
        Container relative to which candidate names and paths are defined.
        ``None`` requests resolution without inspecting data.
    schema : Schema
        Schema instance whose attributes include concrete field overrides.
    mapped_fields : mapping
        Read-only resolution records available to the current mapping.
    """

    data_source: Any
    schema: Schema
    mapped_fields: MappingABC[Mapping, MappedField]


@dataclass
class Schema:
    """Define semantic names for entities that may occur in data.

    Each field describes possible representations of an entity, such as a
    variable, attribute, dimension, or subtree. Use these fields with a mapper
    to access data through consistent names across storage formats.

    Examples
    --------
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class MySchema(Schema):
    ...     field1: Mapping = NameMapping('physical_name')
    ...     field2: Mapping = NameMapping(('alt1', 'alt2'))
    """

    _path_field_names: ClassVar[dict[int, dict[type[Schema], str]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Record path mappings declared by this schema class."""
        super().__init_subclass__(**kwargs)
        for name in get_annotations(cls):
            mapping = vars(cls).get(name)
            if isinstance(mapping, NameMapping) and all(
                candidate.location == FieldLocation.path
                for candidate in mapping.candidates
            ):
                Schema._path_field_names.setdefault(id(mapping), {}).setdefault(
                    cls, name
                )

    def _get_path_field_name(self, mapping: NameMapping) -> str | None:
        """Return the schema attribute associated with a path declaration."""
        names = {
            owner: name
            for owner, name in Schema._path_field_names.get(id(mapping), {}).items()
            if isinstance(self, owner)
        }
        if not names:
            return None
        if len(names) == 1:
            return next(iter(names.values()))
        return names[min(names, key=type(self).__mro__.index)]

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
