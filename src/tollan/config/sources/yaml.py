"""YAML file configuration source."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import field_validator, model_validator

from .base import ConfigSourceBase

if TYPE_CHECKING:
    from .base import DictConfigT

__all__ = ["YamlConfigSource"]


class YamlConfigSource(ConfigSourceBase):
    """Configuration source from YAML file.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    ...     _ = f.write("key: value")
    ...     path = f.name
    >>> src = YamlConfigSource(order=0, source=Path(path))
    >>> src.format
    'yaml'
    >>> src.load()
    {'key': 'value'}
    """

    format: Literal["yaml"] = "yaml"
    """Format identifier, always 'yaml'"""
    source: Path
    """Path to YAML file"""

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
    def _validate_name(self) -> YamlConfigSource:
        """Auto-infer name if not provided.

        Returns
        -------
        YamlConfigSource
            Self with name set to source filename if name was None
        """
        if self.name is None:
            object.__setattr__(self, "name", self.source.name)
        return self

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration from YAML file.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary (unused, for signature compatibility)

        Returns
        -------
        dict[str, Any]
            Configuration dictionary

        Raises
        ------
        ValueError
            If source is not enabled for context
        FileNotFoundError
            If YAML file doesn't exist
        """
        if not self.is_enabled_for(context):
            msg = f"Source '{self.name}' is not enabled for context: {context}"
            raise ValueError(msg)

        with Path(self.source).open() as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
