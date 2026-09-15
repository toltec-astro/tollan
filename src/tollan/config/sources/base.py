"""Base classes and utilities for configuration sources."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from pydantic import BaseModel, PrivateAttr
from simpleeval import NameNotDefined, simple_eval

from ...utils.log import logger

__all__ = [
    "ConfigSourceBase",
    "DictConfigT",
    "FileConfigSourceBase",
]


type DictConfigT = dict[str | int, Any]


class ConfigSourceBase(BaseModel):
    """Base class for configuration sources.

    Common attributes and behavior for all config source types.
    """

    model_config = {"frozen": True}

    order: int
    name: str | None = None
    enabled: bool = True
    enable_if: str | None = None

    def is_enabled_for(self, context: dict[str, Any] | None = None) -> bool:
        """Check if this source is enabled for the given context.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary for evaluating enable_if condition

        Returns
        -------
        bool
            True if source should be loaded, False otherwise
        """
        if not self.enabled:
            return False

        if self.enable_if is None:
            return True

        if context is None:
            context = {}

        # Evaluate enable_if expression using safe eval
        try:
            result = _safe_eval(self.enable_if, context)
            return bool(result)
        except (ValueError, NameError, NameNotDefined, SyntaxError) as e:
            logger.warning(
                f"Failed to evaluate enable_if '{self.enable_if}' "
                f"with context {context}: {e}",
            )
            return False

    def enable_cache(self, *, enabled: bool = True) -> None:
        """Configure cached reads, if the source has any."""

    def invalidate_cache(self) -> None:
        """Clear cached reads, if the source has any."""

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration data from this source.

        Must be implemented by subclasses.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary for conditional loading

        Returns
        -------
        DictConfigT
            Configuration dictionary
        """
        raise NotImplementedError


class FileConfigSourceBase(ConfigSourceBase):
    """Base class for configuration files with cached parsing.

    Subclasses implement `_read` to return a configuration dictionary.
    `load` checks source conditions on every call and reuses the parsed data
    until `invalidate_cache` is called or caching is disabled.
    """

    _cache_enabled: bool = PrivateAttr(default=True)

    @cached_property
    def _data(self) -> DictConfigT:
        return self._read()

    def _read(self) -> DictConfigT:
        """Read and parse the file without evaluating configuration conditions."""
        raise NotImplementedError

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Return parsed file data if enabled for context, reusing a cached read.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Values used to evaluate the source's enable_if condition.

        Returns
        -------
        DictConfigT
            Parsed configuration. Treat the returned data as read-only.

        Raises
        ------
        ValueError
            If the source is disabled for the supplied context.
        """
        if not self.is_enabled_for(context):
            msg = f"Source '{self.name}' is not enabled for context: {context}"
            raise ValueError(msg)
        return self._data if self._cache_enabled else self._read()

    def enable_cache(self, *, enabled: bool = True) -> None:
        """Enable or disable reuse of parsed file data.

        Parameters
        ----------
        enabled : bool, optional
            Whether to cache parsed data, by default True. False discards any
            cached data and makes each enabled load read the file again.
        """
        self._cache_enabled = enabled
        if not enabled:
            self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Discard parsed data so the next enabled load rereads the file.

        Does not read the file immediately or change the cache setting.
        """
        self.__dict__.pop("_data", None)


def _safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """Safely evaluate an expression using simpleeval.

    Uses the simpleeval library for safe expression evaluation without eval().
    Supports comparison operators, boolean logic, and basic operations.

    Parameters
    ----------
    expr : str
        Expression to evaluate
    context : dict[str, Any]
        Variables available in the expression (passed as 'names' to simpleeval)

    Returns
    -------
    Any
        Result of the expression

    Raises
    ------
    ValueError
        If expression contains disallowed operations
    NameError
        If variable not found in context
    """
    try:
        return simple_eval(expr, names=context)
    except NameError as e:
        msg = f"Variable not found in context: {e}"
        raise NameError(msg) from e
