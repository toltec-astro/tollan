"""Base classes and utilities for configuration sources."""

from __future__ import annotations

from enum import StrEnum, auto
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import pandas as pd
from pydantic import BaseModel, PrivateAttr

from ...utils.log import logger
from ..types.path import _path_metadata

if TYPE_CHECKING:
    from . import ConfigSourceList

__all__ = [
    "ConfigSourceBase",
    "ConfigSourceFormat",
    "DictConfigT",
    "FileConfigSourceBase",
]


_SOURCE_PATH_METADATA = _path_metadata(
    exists=False, resolve=False, root_path_key="config_source_root_path"
)
_ConfigSourcePath = Annotated[Path, *_SOURCE_PATH_METADATA]
"""A source-file path relative to the config_source_root_path context value."""


#: Configuration values keyed by names or integer list-update positions.
type DictConfigT = dict[str | int, Any]


class ConfigSourceFormat(StrEnum):
    """Supported configuration source formats."""

    yaml = auto()
    envfile = auto()
    dict = auto()
    list = auto()


class ConfigSourceBase(BaseModel):
    """Base class for configuration sources.

    Common attributes and behavior for all config source types.
    """

    model_config = {"frozen": True}

    order: int
    """Merge priority within the list; later sources override earlier ones."""
    name: str | None = None
    """Optional source label for lookup and diagnostics."""
    enabled: bool = True
    """Whether the source may contribute configuration."""
    enable_if: str | None = None
    """Trusted pandas query expression evaluated against the loading context."""

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
        """Configure cached reads, if the source has any.

        Parameters
        ----------
        enabled : bool, optional
            Reuse file read results, by default True. Dictionary sources have
            no read cache. This base implementation does nothing.
        """

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

    Subclasses implement `_read` to return a dictionary or a source list.
    `load` checks source conditions on every call and reuses the parsed data
    until `invalidate_cache` is called or caching is disabled. Source lists
    are evaluated with the current context on each load.
    """

    _cache_enabled: bool = PrivateAttr(default=True)

    @cached_property
    def _data(self) -> DictConfigT | ConfigSourceList:
        return self._read()

    def _read(self) -> DictConfigT | ConfigSourceList:
        """Read and parse the file without evaluating configuration conditions."""
        raise NotImplementedError

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration for the context, reusing cached parsed data.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Values used to evaluate the source's enable_if condition.

        Returns
        -------
        DictConfigT
            Configuration dictionary, merging contained sources if present.
            Treat the returned data as read-only.

        Raises
        ------
        ValueError
            If the source is disabled for the supplied context.
        """
        data = self._load_data(context)
        if isinstance(data, dict):
            return data
        return data.load(context=context)

    def _load_data(
        self, context: dict[str, Any] | None = None
    ) -> DictConfigT | ConfigSourceList:
        """Return cached file contents without merging a contained source list."""
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
