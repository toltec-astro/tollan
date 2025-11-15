"""Nested list configuration source."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import WithJsonSchema, field_validator, model_validator

from .base import ConfigSourceBase

if TYPE_CHECKING:
    from . import ConfigSourceList
    from .base import DictConfigT

__all__ = ["ListConfigSource"]


class ListConfigSource(ConfigSourceBase):
    """Configuration source from nested list of sources.

    This allows hierarchical composition of config sources.
    The source can be a ConfigSourceList, or a list/dict that will
    be validated into a ConfigSourceList.

    Examples
    --------
    >>> from . import ConfigSourceList
    >>> from .dict_ import DictConfigSource
    >>> sources = ConfigSourceList(data=[
    ...     DictConfigSource(order=0, source={"base": True}),
    ...     DictConfigSource(order=1, source={"override": True})
    ... ])
    >>> src = ListConfigSource(order=0, source=sources)
    >>> src.format
    'list'
    >>> src.load()
    {'base': True, 'override': True}
    """

    format: Literal["list"] = "list"
    """Format identifier, always 'list'"""
    source: Annotated[
        "ConfigSourceList",  # rebuilt after ConfigSourceList
        WithJsonSchema({"type": "object"}),
    ]
    """Nested list of configuration sources"""

    @field_validator("source", mode="before")
    @classmethod
    def _validate_source(cls, v: Any) -> ConfigSourceList:
        """Convert list/dict to ConfigSourceList if needed.

        Parameters
        ----------
        v : Any
            Source as ConfigSourceList, list, or dict

        Returns
        -------
        ConfigSourceList
            Validated source list
        """
        # Import here to avoid circular import
        from . import ConfigSourceList  # noqa: PLC0415

        if isinstance(v, ConfigSourceList):
            return v
        # Use ConfigSourceList's validator to handle list/dict
        return ConfigSourceList.model_validate(v)

    @model_validator(mode="after")
    def _validate_name(self) -> ListConfigSource:
        """Auto-infer name if not provided.

        Returns
        -------
        ListConfigSource
            Self with name set to source name or generated ID
        """
        if self.name is None:
            name = self.source.name or f"list_{id(self.source)}"
            object.__setattr__(self, "name", name)
        return self

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration from nested source list.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary (passed to nested sources)

        Returns
        -------
        DictConfigT
            Merged configuration dictionary

        Raises
        ------
        ValueError
            If source is not enabled for context
        """
        if not self.is_enabled_for(context):
            msg = f"Source '{self.name}' is not enabled for context: {context}"
            raise ValueError(msg)

        return self.source.load(context)
