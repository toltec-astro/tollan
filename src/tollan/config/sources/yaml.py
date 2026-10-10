"""YAML file configuration source."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import model_validator

from .base import FileConfigSourceBase, _ConfigSourcePath
from .envfile import ENV_NAMESPACE_DEFAULT

if TYPE_CHECKING:
    from pydantic import ValidationInfo

    from . import ConfigSourceList
    from .base import DictConfigT

__all__ = ["YamlConfigSource"]


class YamlConfigSource(FileConfigSourceBase):
    """Configuration source from YAML file.

    Accepts a configuration mapping or a list of source declarations. Parsed
    mappings and source lists are cached; list conditions are evaluated on each
    load. Relative filenames in a source list use the containing YAML file's
    directory.
    Paths inside configuration values are left unchanged for typed validation.
    Their validation root is not inferred from this file's location.

    Empty files produce an empty dictionary. Other document types raise
    ValueError rather than silently contributing no settings.
    Loading a missing file raises FileNotFoundError; invalid YAML raises
    yaml.YAMLError.

    Examples
    --------
    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory) / "settings.yaml"
    ...     _ = path.write_text("key: value")
    ...     src = YamlConfigSource(order=0, source=path)
    ...     print(src.format, src.load())
    yaml {'key': 'value'}
    """

    format: Literal["yaml"] = "yaml"
    """Format identifier, always 'yaml'"""
    source: _ConfigSourcePath
    """Path to YAML file"""
    env_namespace: str | None = ENV_NAMESPACE_DEFAULT
    """Default namespace for dotenv sources included by this file."""

    @model_validator(mode="before")
    @classmethod
    def _fill_env_namespace_default(cls, data: Any, info: ValidationInfo) -> Any:
        """Fill an omitted namespace from validation context."""
        context = info.context or {}
        if (
            isinstance(data, dict)
            and "env_namespace" not in data
            and "env_namespace" in context
        ):
            return data | {"env_namespace": context["env_namespace"]}
        return data

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

            return resolve_config_sources(
                data,
                env_namespace=self.env_namespace,
                config_source_root_path=self.source.resolve().parent,
            )
        msg = f"Expected a configuration mapping or source list in {self.source}"
        raise ValueError(msg)
