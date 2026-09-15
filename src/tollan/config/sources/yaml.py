"""YAML file configuration source."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import field_validator, model_validator

from .base import FileConfigSourceBase

if TYPE_CHECKING:
    from .base import DictConfigT

__all__ = ["YamlConfigSource"]


class YamlConfigSource(FileConfigSourceBase):
    """Configuration source from YAML file.

    Parses the file with `yaml.safe_load` and caches the resulting dictionary.
    Empty files and non-mapping YAML documents produce an empty dictionary.
    Loading a missing file raises FileNotFoundError; invalid YAML raises
    yaml.YAMLError.

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

    def _read(self) -> DictConfigT:
        """Read and parse the YAML file."""
        with Path(self.source).open() as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
