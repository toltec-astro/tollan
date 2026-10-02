"""Context-aware Pydantic path annotations."""

from __future__ import annotations

from functools import cache, partial
from pathlib import Path
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


def _prepare_path(value: Any, info: ValidationInfo) -> Path | str:
    """Apply an optional validation-context root before Path validation."""
    if not isinstance(value, str | Path):
        error = PydanticCustomError(
            "path_type",
            "Input should be a string or Path object",
        )
        raise error
    rootpath = None if info.context is None else info.context.get("rootpath")
    if rootpath is None:
        result = Path(value)
    else:
        try:
            result = Path(rootpath).joinpath(value)
        except TypeError as e:
            error = PydanticCustomError(
                "path_root_type",
                "Validation context rootpath should be a string or Path object",
            )
            raise error from e
    return str(result) if info.mode == "json" else result


def _validate_path(
    path: Path,
    *,
    exists: bool,
    resolve: bool,
) -> Path:
    """Apply the constraints not already supplied by Pydantic path types."""
    if resolve:
        path = path.expanduser().resolve()
    if exists and not path.exists():
        error = PydanticCustomError("path_not_found", "Path does not exist")
        raise error
    return path


@cache
def _path_metadata(
    *,
    exists: bool,
    resolve: bool,
) -> tuple[Any, ...]:
    return (
        BeforeValidator(_prepare_path, json_schema_input_type=_PATH_JSON_INPUT),
        AfterValidator(
            partial(
                _validate_path,
                exists=exists,
                resolve=resolve,
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
        A validation-context ``rootpath`` is applied before these checks.

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
