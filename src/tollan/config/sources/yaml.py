"""YAML file configuration source."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import field_validator, model_validator

from .base import FileConfigSourceBase
from .envfile import ENV_NAMESPACE_DEFAULT

if TYPE_CHECKING:
    from . import ConfigSourceList
    from .base import DictConfigT

__all__ = ["YamlConfigSource"]


class YamlConfigSource(FileConfigSourceBase):
    """Configuration source from YAML file.

    Accepts a configuration mapping or a list of source declarations. Parsed
    mappings and source lists are cached; list conditions are evaluated on each
    load. Relative source paths are resolved against this file's directory.
    Paths inside configuration values are left unchanged for typed validation.
    Their validation root is not inferred from this file's location.

    Empty files produce an empty dictionary. Other document types raise
    ValueError rather than silently contributing no settings.
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
    env_namespace: str | None = ENV_NAMESPACE_DEFAULT
    """Default namespace for dotenv sources included by this file."""

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

    def _read(self) -> DictConfigT | ConfigSourceList:
        """Read and parse the YAML file."""
        with Path(self.source).open() as f:
            data = yaml.safe_load(f)
        if data is None:
            return {}
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            from . import resolve_config_sources  # noqa: PLC0415

            _resolve_source_paths(data, self.source.resolve().parent)
            return resolve_config_sources(data, env_namespace=self.env_namespace)
        msg = f"Expected a configuration mapping or source list in {self.source}"
        raise ValueError(msg)


def _resolve_source_paths(declarations: list, base_path: Path) -> None:
    """Resolve file references in freshly parsed YAML source declarations."""
    for declaration in declarations:
        if not isinstance(declaration, dict):
            msg = f"Source declarations in {base_path} must be mappings"
            # Invalid file contents, not an invalid argument to this API.
            raise ValueError(msg)  # noqa: TRY004
        source = declaration.get("source")
        if isinstance(source, str):
            declaration["source"] = base_path / source
        elif isinstance(source, list):
            _resolve_source_paths(source, base_path)
        elif declaration.get("format") == "list" and isinstance(source, dict):
            data = source.get("data")
            if isinstance(data, list):
                _resolve_source_paths(data, base_path)
