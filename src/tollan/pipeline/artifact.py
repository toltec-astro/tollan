"""Selected operation data with specifications for persistence or exchange.

Artifacts can select a portion or all of an operation's data context. Define an
``ArtifactSpec`` with a concrete input signature and a ``write`` method. Its call
prepares ordinary data; add that data and its effective spec to an
``ArtifactContext`` for later use or export:

>>> class TextSpec(ArtifactSpec[str]):
...     prefix: str = "Result: "
...     def __call__(self, value: int) -> str:
...         return f"{self.prefix}{value}"
>>> spec = TextSpec()
>>> artifacts = ArtifactContext()
>>> entry = artifacts.add(spec, spec(3))
>>> artifacts[TextSpec].data
'Result: 3'
>>> entry.spec is spec
True

An instance lookup includes its configured alias; a class selects the primary
entry. Adding the same key replaces that entry. The context does not construct,
display, or write artifacts. Each retained spec owns materialization of its
object at a destination supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 -- ArtifactFile is also a Pydantic field type.
from typing import Any, overload

from pydantic import Field

from ..config import FrozenBaseModel
from ..utils.py import getname

__all__ = ["Artifact", "ArtifactContext", "ArtifactFile", "ArtifactSpec"]


@dataclass(frozen=True)
class ArtifactFile:
    """Written artifact file or directory.

    Parameters
    ----------
    path : pathlib.Path
        Destination that was successfully written.
    format : str
        Representation identifier, such as ``html``, ``png``, or ``zarr``.
    """

    path: Path
    format: str


class ArtifactSpec[DataT](FrozenBaseModel):
    """Configuration for producing and materializing an artifact.

    Parameters
    ----------
    alias : str or None, optional
        Label for retaining multiple outputs from this spec class. None selects
        its primary entry in an ArtifactContext.

    Notes
    -----
    Subclasses define their own ``__call__`` input signature and return an object
    of the bound data type. Implement ``write`` to materialize an existing object.
    Construction and writing are separate operations. A specification can also
    compose named specifications and return an ArtifactContext.

    Keep the effective spec with its produced object. Resolve shared settings
    before construction so later export uses those same settings. Live results
    belong to ArtifactContext, not to this frozen configuration.
    """

    alias: str | None = Field(default=None, description="Artifact invocation label.")

    @classmethod
    def get_context_key(cls, *, alias: str | None = None) -> str:
        """Return the key for an artifact invocation.

        Parameters
        ----------
        alias : str or None, optional
            Invocation label; None selects the primary artifact.

        Returns
        -------
        str
            Qualified spec name, including the alias when supplied.
        """
        name = getname(cls)
        return name if alias is None else f"{name}:{alias}"

    def write(self, data: DataT, *, path: Path) -> list[ArtifactFile]:
        """Materialize an already produced object at a caller-owned destination.

        Parameters
        ----------
        data : DataT
            Produced object. Required lazy source resources must remain open
            until writing finishes.
        path : pathlib.Path
            Destination. The concrete spec defines its file/directory convention
            and supported representations.

        Returns
        -------
        list of ArtifactFile
            Successfully written files or directories. A disabled export may
            return an empty list. Publication and index updates belong to callers.

        Raises
        ------
        NotImplementedError
            The concrete spec has not implemented materialization.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class Artifact[DataT]:
    """Selected or assembled data paired with its effective specification.

    Parameters
    ----------
    data : DataT
        Native data selected or assembled for persistence or exchange, retained
        by reference.
    spec : ArtifactSpec
        Effective configuration used to produce the object. Its ``write`` method
        materializes this data without repeating construction.
    """

    data: DataT
    spec: ArtifactSpec[DataT]


class ArtifactContext(Mapping[str, Artifact[Any]]):
    """Collection of selected artifacts with typed spec-class lookup.

    Parameters
    ----------
    artifacts : iterable of Artifact, optional
        Initial entries. Later entries with the same class and alias replace
        earlier ones. The default context is empty.

    Notes
    -----
    Use a spec class for its primary artifact, a configured spec instance for
    its alias, or the string returned by ``get_context_key``. Iteration yields
    those string keys. Entries retain references to both data and configuration.
    Pickle support depends on those objects and their source resources.
    """

    def __init__(self, artifacts: Iterable[Artifact[Any]] = ()) -> None:
        self._entries = {self._key(a.spec): a for a in artifacts}

    @staticmethod
    @overload
    def _key(key: str | type[ArtifactSpec] | ArtifactSpec) -> str: ...

    @staticmethod
    @overload
    def _key(key: object) -> object: ...

    @staticmethod
    def _key(key: object) -> object:
        if isinstance(key, ArtifactSpec):
            return key.get_context_key(alias=key.alias)
        if isinstance(key, type) and issubclass(key, ArtifactSpec):
            return key.get_context_key()
        return key

    def add[DataT](self, spec: ArtifactSpec[DataT], data: DataT) -> Artifact[DataT]:
        """Retain an object and its effective spec without copying either.

        Parameters
        ----------
        spec : ArtifactSpec
            Producing spec, including its effective settings and alias.
        data : DataT
            Object produced with those settings.

        Returns
        -------
        Artifact
            Stored entry. Replaces an existing entry for the same class and alias.
        """
        artifact = Artifact(data=data, spec=spec)
        self._entries[self._key(spec)] = artifact
        return artifact

    @overload
    def __getitem__[DataT](
        self, key: type[ArtifactSpec[DataT]] | ArtifactSpec[DataT]
    ) -> Artifact[DataT]: ...

    @overload
    def __getitem__(self, key: str) -> Artifact[Any]: ...

    def __getitem__(
        self, key: str | type[ArtifactSpec] | ArtifactSpec
    ) -> Artifact[Any]:
        return self._entries[self._key(key)]

    @overload
    def get[DataT](
        self,
        key: type[ArtifactSpec[DataT]] | ArtifactSpec[DataT],
    ) -> Artifact[DataT] | None: ...

    @overload
    def get[DataT, DefaultT](
        self, key: type[ArtifactSpec[DataT]] | ArtifactSpec[DataT], default: DefaultT
    ) -> Artifact[DataT] | DefaultT: ...

    @overload
    def get(self, key: object) -> Artifact[Any] | None: ...

    @overload
    def get[DefaultT](
        self, key: object, default: DefaultT
    ) -> Artifact[Any] | DefaultT: ...

    def get(self, key: object, default: Any = None) -> Any:
        """Return an artifact, or the supplied default when its key is absent.

        Parameters
        ----------
        key : type of ArtifactSpec, ArtifactSpec, or str
            Spec class, configured instance, or qualified context key.
        default : object, optional
            Missing-key result; defaults to None.

        Returns
        -------
        Artifact or object
            Typed entry for a spec lookup, or the missing-key default.
        """
        return self._entries.get(self._key(key), default)

    def __contains__(self, key: object) -> bool:
        return self._key(key) in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
