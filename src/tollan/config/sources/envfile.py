"""Environment file (.env) configuration source using python-dotenv."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dotenv import dotenv_values
from pydantic import field_validator, model_validator

from .base import ConfigSourceBase

if TYPE_CHECKING:
    from .base import DictConfigT

__all__ = ["EnvFileConfigSource"]


class EnvFileConfigSource(ConfigSourceBase):
    r"""Configuration source from .env file.

    Uses python-dotenv to parse .env files. Supports variable expansion
    and default values.

    Examples
    --------
    >>> from pathlib import Path
    >>> from tollan.config.sources import EnvFileConfigSource
    >>> # Basic usage (requires actual .env file)
    >>> src = EnvFileConfigSource(order=0, source=Path(".env"))  # doctest: +SKIP
    >>> src.format  # doctest: +SKIP
    'envfile'
    """

    format: Literal["envfile"] = "envfile"
    """Format identifier, always 'envfile'"""
    source: Path
    """Path to .env file"""
    encoding: str = "utf-8"
    """File encoding"""
    interpolate: bool = True
    """Enable variable expansion"""

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

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration from .env file.

        Uses python-dotenv's dotenv_values() to parse the file.
        Returns a dictionary with all key-value pairs from the file.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary (unused, for signature compatibility)

        Returns
        -------
        dict[str, Any]
            Configuration dictionary with string values

        Raises
        ------
        ValueError
            If source is not enabled for context
        FileNotFoundError
            If .env file doesn't exist

        Notes
        -----
        All values are returned as strings (as they appear in the .env file).
        Type conversion should be handled by the consumer.

        Variable expansion is supported if interpolate=True:
        - ${VAR} expands to the value of VAR
        - ${VAR:-default} expands to value of VAR or "default" if not set
        """
        if not self.is_enabled_for(context):
            msg = f"Source '{self.name}' is not enabled for context: {context}"
            raise ValueError(msg)

        # Use dotenv_values to parse the file
        # It returns a dict[str, str | None] where None means variable without value
        data = dotenv_values(
            self.source,
            encoding=self.encoding,
            interpolate=self.interpolate,
        )

        # Filter out None values (variables without values)
        # Convert to regular dict[str, Any] for compatibility
        return {k: v for k, v in data.items() if v is not None}
