"""Base model classes for configuration.

This module provides base Pydantic model classes with common configuration
for the tollan config system.
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict

from ..utils.yaml import yaml_dump, yaml_load

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["FrozenBaseModel"]


class FrozenBaseModel(BaseModel):
    """Base model class with immutability and YAML support.

    Provides common configuration for astronomy data models:
    - Frozen by default
    - Strict type validation
    - YAML loading/dumping support
    - Custom JSON schema generation

    Examples
    --------
    >>> class MyConfig(FrozenBaseModel):
    ...     name: str
    ...     value: int
    >>> config = MyConfig(name="test", value=42)
    >>> yaml_str = config.model_dump_yaml()
    >>> loaded = MyConfig.model_validate_yaml(yaml_str)
    """

    yaml_load: ClassVar = staticmethod(yaml_load)
    yaml_dump: ClassVar = staticmethod(yaml_dump)

    model_config = ConfigDict(
        frozen=True,
        validate_default=True,
        ignored_types=(cached_property,),
        strict=True,
    )

    def model_dump_yaml(self, **kwargs: Any) -> str:
        """Dump model as YAML.

        Parameters
        ----------
        **kwargs
            Arguments passed to model_dump()

        Returns
        -------
        str
            YAML representation of model
        """
        d = self.model_dump(**kwargs)
        return self.yaml_dump(d)

    @classmethod
    def model_validate_yaml(
        cls,
        yaml_source: str | Path,
        **kwargs: Any,
    ) -> Self:
        """Validate model from YAML.

        Parameters
        ----------
        yaml_source : str | Path
            YAML source to load
        **kwargs
            Arguments passed to model_validate()

        Returns
        -------
        Self
            Validated model instance
        """
        d = cls.yaml_load(yaml_source)
        return cls.model_validate(d, **kwargs)

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Generate JSON schema using custom schema generator.

        This uses our custom GenerateJsonSchema which knows how to
        serialize astronomy types (Time, Quantity) in default values.

        Parameters
        ----------
        *args
            Arguments passed to BaseModel.model_json_schema()
        **kwargs
            Keyword arguments passed to BaseModel.model_json_schema()

        Returns
        -------
        dict
            JSON schema for the model
        """
        from .types.pydantic import GenerateJsonSchema  # noqa: PLC0415

        kwargs.setdefault("schema_generator", GenerateJsonSchema)
        return super().model_json_schema(*args, **kwargs)
