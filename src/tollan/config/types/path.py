"""Path validators and type aliases."""

from __future__ import annotations

import dataclasses
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic.types import PathType as _PathType
from pydantic_core import core_schema

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler, ValidationInfo
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import CoreSchema

__all__ = [
    "AbsAnyPath",
    "AbsDirectoryPath",
    "AbsFilePath",
    "AnyPath",
    "PathValidator",
]


@dataclasses.dataclass(frozen=True)
class PathValidator:
    """Validator for Path types with rootpath context support.

    This validator provides automatic handling of rootpath from validation context,
    optional path resolution, and existence/type checking. It follows the validation
    chain: rootpath → resolve → exists → type check.

    Parameters
    ----------
    path_type : None | Literal["file", "dir", "new"]
        Type of path to validate:
        - "file": Must be an existing file
        - "dir": Must be an existing directory
        - "new": Must not exist, but parent must exist
        - None: No type-specific validation
    exists : bool, default=True
        Whether to check if path exists (ignored for path_type="new")
    resolve : bool, default=True
        Whether to resolve path to absolute (expanduser + resolve)

    Examples
    --------
    >>> from pydantic import BaseModel
    >>> from pathlib import Path
    >>> class Config(BaseModel):
    ...     file: Annotated[Path, PathValidator(exists=False)]
    >>> # Validate with rootpath context
    >>> config = Config.model_validate(
    ...     {"file": "data.txt"},
    ...     context={"rootpath": "/base/dir"}
    ... )
    >>> str(config.file)
    '/base/dir/data.txt'
    """

    path_type: None | Literal["file", "dir", "new"] = None
    exists: bool = True
    resolve: bool = True

    def __post_init__(self) -> None:
        """Adjust exists flag for 'new' path type."""
        if self.path_type == "new":
            # For 'new' paths, exists check is handled by _PathType
            object.__setattr__(self, "exists", False)

    def __get_pydantic_json_schema__(
        self,
        _core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Generate JSON schema for path field."""
        if self._super is not None:
            return self._super.__get_pydantic_json_schema__(_core_schema, handler)
        js = handler(_core_schema)
        js.update({"type": "string", "format": "path"})
        return js

    def __get_pydantic_core_schema__(
        self,
        source: type[Any],
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """Build validation chain: rootpath → resolve → exists → type check."""
        # Step 1: Handle rootpath from context (before validation)
        schema0 = core_schema.with_info_before_validator_function(
            self.validate_path_rootpath,
            schema=handler(source),
        )

        # Step 2: Resolve if requested (after base Path validation)
        if self.resolve:
            schema1 = core_schema.with_info_after_validator_function(
                self.resolve_path,
                schema=schema0,
            )
        else:
            schema1 = schema0

        # Step 3: Check exists if requested
        if self.exists:
            schema2 = core_schema.with_info_after_validator_function(
                self.validate_exists,
                schema=schema1,
            )
        else:
            schema2 = schema1

        # Step 4: Apply type-specific validation (file/dir/new)
        if self._super is not None:
            return core_schema.chain_schema(
                [
                    schema2,
                    self._super.__get_pydantic_core_schema__(
                        source=source,
                        handler=handler,
                    ),
                ],
            )

        return schema2

    @cached_property
    def _super(self) -> _PathType | None:
        """Get pydantic's native PathType validator if path_type is specified."""
        if self.path_type is not None:
            return _PathType(self.path_type)
        return None

    @staticmethod
    def validate_exists(path: Path, info: ValidationInfo) -> Path:
        """Ensure path exists.

        Parameters
        ----------
        path : Path
            Path to validate
        info : ValidationInfo
            Pydantic validation info

        Returns
        -------
        Path
            The validated path if it exists

        Raises
        ------
        ValueError
            If path does not exist
        """
        if path.exists():
            return path
        msg = f"Path {path} does not exist."
        raise ValueError(msg)

    @staticmethod
    def validate_path_rootpath(path: Any, info: ValidationInfo) -> Path:
        """Handle rootpath from validation context.

        This runs before Path validation, joining the input with rootpath
        from context if present.

        Parameters
        ----------
        path : Any
            Input path (string or Path object)
        info : ValidationInfo
            Pydantic validation info with optional rootpath in context

        Returns
        -------
        Path
            Path joined with rootpath if present, otherwise original path

        Raises
        ------
        TypeError
            If path is not a string or Path object
        """
        if not isinstance(path, str | Path):
            msg = f"invalid path data type {type(path)}"
            raise TypeError(msg)

        if info.context is not None:
            rootpath = info.context.get("rootpath", None)
        else:
            rootpath = None

        if rootpath is not None:
            return Path(rootpath).joinpath(path)
        return Path(path)

    @staticmethod
    def resolve_path(path: Path, info: ValidationInfo) -> Path:
        """Resolve path to absolute.

        Expands user home directory (~) and resolves to absolute path.

        Parameters
        ----------
        path : Path
            Path to resolve
        info : ValidationInfo
            Pydantic validation info (unused but required by interface)

        Returns
        -------
        Path
            Absolute path with user home directory expanded
        """
        return path.expanduser().resolve()


# Path type aliases with automatic rootpath support

AnyPath = Annotated[Path, PathValidator(path_type=None, exists=False, resolve=False)]
"""Basic Path with no validation or resolution."""

AbsFilePath = Annotated[
    Path,
    PathValidator(path_type="file", exists=True, resolve=True),
]
"""Path to an existing file, resolved to absolute, with automatic rootpath support."""

AbsDirectoryPath = Annotated[
    Path,
    PathValidator(path_type="dir", exists=True, resolve=True),
]
"""Path to an existing directory, resolved to absolute.

Automatically supports rootpath resolution.
"""

AbsAnyPath = Annotated[Path, PathValidator(path_type=None, exists=False, resolve=True)]
"""Any path resolved to absolute (no existence check).

Automatically supports rootpath resolution.
"""
