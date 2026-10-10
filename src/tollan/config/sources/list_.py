"""Nested list configuration source."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import WithJsonSchema, field_validator, model_validator

from .base import ConfigSourceBase

if TYPE_CHECKING:
    from pydantic import ValidationInfo

    from . import ConfigSourceList
    from .base import DictConfigT

__all__ = ["ListConfigSource"]


class ListConfigSource(ConfigSourceBase):
    """Configuration source from nested list of sources.

    This allows hierarchical composition of config sources.
    The source can be a ConfigSourceList, a list of source declarations, or a
    dictionary. A dictionary without ``data`` supplies settings; one with
    ``data`` declares a source collection and optional ``name``.

    Examples
    --------
    >>> from tollan.config.sources import ConfigSourceList, DictConfigSource
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
    def _validate_source(cls, v: Any, info: ValidationInfo) -> ConfigSourceList:
        """Validate nested shorthand with the source-list context."""
        # Import here to avoid circular import
        from . import ConfigSourceList  # noqa: PLC0415

        if isinstance(v, ConfigSourceList):
            return v
        return ConfigSourceList.model_validate(
            v,
            context={**(info.context or {}), "config_source_implicit_order": True},
        )

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

    def enable_cache(self, *, enabled: bool = True) -> None:
        """Configure read caching for the contained sources.

        Parameters
        ----------
        enabled : bool, optional
            Reuse file reads in this list and its nested lists, by default True.
        """
        self.source.enable_cache(enabled=enabled)

    def invalidate_cache(self) -> None:
        """Clear cached reads in the contained sources."""
        self.source.invalidate_cache()

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
