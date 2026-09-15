"""Base classes and utilities for configuration sources."""

from __future__ import annotations

from functools import cached_property
from typing import Any

import pandas as pd
from pydantic import BaseModel, PrivateAttr

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
        """Evaluate whether this source is enabled for the given context.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Variable names and values used to evaluate `enable_if`.
            A conditional source is disabled when no context is provided.

        Returns
        -------
        bool
            Whether this source is enabled and its condition matches.
            Undefined variables disable the source; other query errors propagate.

        Notes
        -----
        Conditions use pandas query syntax, including comparison-before-boolean
        precedence for `&` and `|`, and membership with `in` and `not in`.
        Evaluation is not guaranteed to short-circuit.

        Only use trusted configuration expressions. Pandas query evaluation
        is not a security sandbox, even with empty local and global dictionaries.

        Examples
        --------
        >>> source = ConfigSourceBase(
        ...     order=0,
        ...     enable_if='workers >= 4 & environment in ["staging", "production"]',
        ... )
        >>> source.is_enabled_for({"workers": 8, "environment": "production"})
        True
        >>> source.is_enabled_for({"workers": 2, "environment": "production"})
        False
        """
        if not self.enabled:
            return False

        if self.enable_if is None:
            return True

        if context is None:
            logger.debug(
                "Source {} (order={}): disabled by enable_if={!r} "
                "with context=None: no context provided",
                self.name or "<unnamed>",
                self.order,
                self.enable_if,
            )
            return False
        if not isinstance(context, dict):
            msg = "Condition context must be a dictionary."
            raise TypeError(msg)

        tbl_context = pd.DataFrame.from_records([context])
        try:
            result = tbl_context.query(
                self.enable_if, parser="pandas", local_dict={}, global_dict={}
            )
        except pd.errors.UndefinedVariableError as e:
            logger.debug(
                "Source {} (order={}): disabled by enable_if={!r} "
                "with context={!r}: {}",
                self.name or "<unnamed>",
                self.order,
                self.enable_if,
                context,
                e,
            )
            return False
        return not result.empty

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
