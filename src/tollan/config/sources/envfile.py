"""Environment file (.env) configuration source using python-dotenv."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dotenv import dotenv_values
from pydantic import field_validator, model_validator

from .base import FileConfigSourceBase

if TYPE_CHECKING:
    from .base import DictConfigT

__all__ = ["ENV_NAMESPACE_DEFAULT", "EnvFileConfigSource"]

ENV_NAMESPACE_DEFAULT = "_env"
"""Default configuration key containing dotenv values."""


class EnvFileConfigSource(FileConfigSourceBase):
    r"""Configuration source from .env file.

    Uses python-dotenv to parse .env files. Supports variable expansion
    and default values. Values are strings; entries without a value are omitted.
    Set `interpolate=False` to retain variable references literally.
    Parsed values, including environment expansion, are cached until invalidated.
    Values are stored under ``ENV_NAMESPACE_DEFAULT`` by default. Set ``namespace`` to
    another top-level key, or to ``None`` to load values directly at the root.
    Loading does not modify the process environment.

    Notes
    -----
    With interpolation enabled, ``${VAR}`` expands a variable reference and
    ``${VAR:-default}`` supplies a fallback for an unset variable. Type
    conversion is left to the configuration consumer.

    Examples
    --------
    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory) / ".env"
    ...     _ = path.write_text("HOST=localhost\nURL=http://${HOST}\n")
    ...     src = EnvFileConfigSource(order=0, source=path)
    ...     print(src.load()[ENV_NAMESPACE_DEFAULT]["URL"])
    http://localhost
    """

    format: Literal["envfile"] = "envfile"
    """Format identifier, always 'envfile'"""
    source: Path
    """Path to .env file"""
    encoding: str = "utf-8"
    """File encoding"""
    interpolate: bool = True
    """Enable variable expansion"""
    namespace: str | None = ENV_NAMESPACE_DEFAULT
    """Top-level key for parsed values; None loads them at the root."""

    @field_validator("source", mode="before")
    @classmethod
    def _validate_source(cls, v: Any) -> Path:
        """Convert string paths to Path objects.

        Parameters
        ----------
        v : Any
            Source path as string or Path

        Returns
        -------
        Path
            Path object
        """
        if isinstance(v, str):
            return Path(v)
        return v

    @model_validator(mode="after")
    def _validate_name(self) -> EnvFileConfigSource:
        """Auto-infer name if not provided.

        Returns
        -------
        EnvFileConfigSource
            Self with name set to source filename if name was None
        """
        if self.name is None:
            object.__setattr__(self, "name", self.source.name)
        return self

    def _read(self) -> DictConfigT:
        """Read the env file and expand variables using the current environment."""
        # Use dotenv_values to parse the file
        # It returns a dict[str, str | None] where None means variable without value
        data = dotenv_values(
            self.source,
            encoding=self.encoding,
            interpolate=self.interpolate,
        )

        # Omit declarations without values, retaining empty strings.
        values: DictConfigT = {k: v for k, v in data.items() if v is not None}
        return values if self.namespace is None else {self.namespace: values}
