"""Pydantic annotations for filesystem paths and relative subpaths."""

from __future__ import annotations

from functools import cache, partial
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    DirectoryPath,
    Field,
    FilePath,
    NewPath,
    ValidationInfo,
)
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from typing_extensions import TypeForm

__all__ = [
    "AbsAnyPath",
    "AbsDirectoryPath",
    "AbsFilePath",
    "AnyPath",
    "SubPath",
    "path_field",
]

type PathType = Literal["file", "dir", "new"]
_PATH_JSON_INPUT = Annotated[str, Field(json_schema_extra={"format": "path"})]
_PATH_BASE_TYPES: dict[PathType | None, Any] = {
    "file": FilePath,
    "dir": DirectoryPath,
    "new": NewPath,
    None: Path,
}


def _prepare_path(
    value: Any,
    info: ValidationInfo,
    *,
    resolve: bool,
    root_path_key: str,
) -> Path | str:
    """Apply an optional validation-context root before Path validation."""
    if not isinstance(value, str | Path):
        error = PydanticCustomError(
            "path_type",
            "Input should be a string or Path object",
        )
        raise error
    root_path = None if info.context is None else info.context.get(root_path_key)
    if root_path is None:
        result = Path(value)
    else:
        try:
            result = Path(root_path).joinpath(value)
        except TypeError as e:
            error = PydanticCustomError(
                "path_root_type",
                "Validation context {key} should be a string or Path object",
                {"key": root_path_key},
            )
            raise error from e
    if resolve:
        result = result.expanduser().resolve()
    return str(result) if info.mode == "json" else result


def _validate_path(
    path: Path,
    *,
    exists: bool,
) -> Path:
    """Apply the constraints not already supplied by Pydantic path types."""
    if exists and not path.exists():
        error = PydanticCustomError("path_not_found", "Path does not exist")
        raise error
    return path


@cache
def _path_metadata(
    *,
    exists: bool,
    resolve: bool,
    root_path_key: str = "root_path",
) -> tuple[Any, ...]:
    return (
        BeforeValidator(
            partial(_prepare_path, resolve=resolve, root_path_key=root_path_key),
            json_schema_input_type=_PATH_JSON_INPUT,
        ),
        AfterValidator(
            partial(
                _validate_path,
                exists=exists,
            )
        ),
    )


_ANY_PATH_METADATA = _path_metadata(exists=False, resolve=False)
_ABS_TYPED_PATH_METADATA = _path_metadata(exists=False, resolve=True)
_ABS_ANY_PATH_METADATA = _path_metadata(exists=False, resolve=True)

type AnyPath = Annotated[Path, *_ANY_PATH_METADATA]
"""A Path with optional validation-context root and no filesystem checks."""

type AbsFilePath = Annotated[FilePath, *_ABS_TYPED_PATH_METADATA]
"""An existing file resolved to an absolute path."""

type AbsDirectoryPath = Annotated[DirectoryPath, *_ABS_TYPED_PATH_METADATA]
"""An existing directory resolved to an absolute path."""

type AbsAnyPath = Annotated[Path, *_ABS_ANY_PATH_METADATA]
"""Any path resolved to absolute form without an existence check."""


def _validate_subpath(path: PurePosixPath) -> PurePosixPath:
    """Require a relative descendant without parent traversal."""
    if path.anchor or not path.parts or ".." in path.parts:
        msg = f"Expected a relative descendant path, got {str(path)!r}"
        raise ValueError(msg)
    return path


type SubPath = Annotated[
    PurePosixPath, Field(strict=False), AfterValidator(_validate_subpath)
]
"""A relative POSIX descendant path without parent traversal.

Accepts strings and PurePosixPath objects, including in strict models. Redundant
separators and ``.`` components are removed. The containing directory itself
is not a descendant. No validation-context root_path, user expansion, filesystem
checks, or symlink resolution is applied.
"""


def path_field(
    *,
    path_type: PathType | None = None,
    exists: bool = True,
    resolve: bool = True,
) -> TypeForm[Path]:
    """Build a context-aware Path annotation with filesystem constraints.

    Parameters
    ----------
    path_type : {'file', 'dir', 'new', None}, optional
        Require an existing file or directory, a new path with an existing
        parent, or an unconstrained Path. Defaults to None.
    exists : bool, optional
        Require existence for an unconstrained Path, by default True.
        Typed paths always apply their own checks regardless of this flag.
    resolve : bool, optional
        Expand the user directory and resolve to absolute form, by default True.
        A validation-context ``root_path`` is applied before these checks.

    Returns
    -------
    typing_extensions.TypeForm
        Path annotation usable by Pydantic models and TypeAdapter.
    """
    base_type = _PATH_BASE_TYPES[path_type]
    # FilePath, DirectoryPath, and NewPath own their filesystem checks and
    # standard Pydantic error messages. Only an unconstrained Path needs the
    # separate generic existence check.
    check_exists = exists and path_type is None
    return Annotated[
        base_type,
        *_path_metadata(exists=check_exists, resolve=resolve),
    ]
