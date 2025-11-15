"""Dictionary configuration source."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import WithJsonSchema

from .base import ConfigSourceBase, DictConfigT

__all__ = ["DictConfigSource"]


class DictConfigSource(ConfigSourceBase):
    """Configuration source from dictionary.

    Keys can be strings or integers. Integer keys are used by rupdate
    to update list items at specific indices.

    Examples
    --------
    >>> from tollan.config.sources import ConfigSourceList
    >>> sources = ConfigSourceList(
    ...     data=[
    ...         {"format": "dict", "source": {"key": "value"}, "order": 1}
    ...     ]
    ... )
    >>> src = sources[0]
    >>> src.format
    'dict'
    >>> src.load()['key']
    'value'
    """

    format: Literal["dict"] = "dict"
    """Format identifier, always 'dict'"""
    source: Annotated[
        DictConfigT,
        WithJsonSchema({"type": "object", "additionalProperties": True}),
    ]
    """Dictionary containing configuration data"""

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration from dictionary.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary (unused, for signature compatibility)

        Returns
        -------
        DictConfigT
            Deep copy of source dictionary

        Raises
        ------
        ValueError
            If source is not enabled for context
        """
        if not self.is_enabled_for(context):
            msg = f"Source '{self.name}' is not enabled for context: {context}"
            raise ValueError(msg)

        return self.source
