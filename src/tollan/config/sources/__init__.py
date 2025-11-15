"""Configuration sources for loading config from various formats."""

from __future__ import annotations

import collections.abc
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self, overload

from loguru import logger
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    WithJsonSchema,
    field_validator,
    model_validator,
)

# Import dict manipulation utility from utils
from ...utils.dict import rupdate

# Import source implementations
from .base import DictConfigT  # noqa: TC001  # downstream models use this
from .dict_ import DictConfigSource
from .envfile import EnvFileConfigSource
from .list_ import ListConfigSource
from .yaml import YamlConfigSource

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pydantic import (
        ValidationInfo,
    )

__all__ = [
    "ConfigSource",
    "ConfigSourceList",
    "DictConfigSource",
    "EnvFileConfigSource",
    "ListConfigSource",
    "YamlConfigSource",
    "resolve_config_sources",
]

# Union type for all config sources
type ConfigSource = Annotated[
    YamlConfigSource | DictConfigSource | EnvFileConfigSource | ListConfigSource,
    Field(discriminator="format"),
]


# ============================================================================
# Cache Configuration
# ============================================================================


@dataclass
class CacheConfig:
    """Configuration for ConfigSourceList caching behavior.

    Attributes
    ----------
        enabled: Whether caching is enabled
        cache: Cache storage (order → loaded data)
        cached_predicate: Predicate to select sources to cache
        exclude_predicate: Predicate to exclude sources from cache
    """

    enabled: bool = False
    cache: dict[int, DictConfigT] = field(default_factory=dict)
    cached_predicate: Callable[[Any], bool] | None = None
    exclude_predicate: Callable[[Any], bool] | None = None

    def should_cache(self, source: Any) -> bool:
        """Check if a source should be cached.

        Parameters
        ----------
        source : Any
            Config source to check

        Returns
        -------
        bool
            True if source should be cached
        """
        if not self.enabled:
            return False

        # Check exclude predicate first
        if self.exclude_predicate and self.exclude_predicate(source):
            return False

        # Check include predicate
        if self.cached_predicate is not None:
            return self.cached_predicate(source)

        # Default: cache all (unless excluded)
        return True

    def get_cache_key(self, source: ConfigSource) -> int:
        """Get cache key for a source.

        Uses order as the key since order is enforced to be unique.

        Parameters
        ----------
        source : ConfigSource
            Config source

        Returns
        -------
        int
            Cache key (order)
        """
        return source.order

    def get(self, source: ConfigSource) -> DictConfigT | None:
        """Get cached data for a source.

        Parameters
        ----------
        source : ConfigSource
            Config source

        Returns
        -------
        DictConfigT | None
            Cached data if available, None otherwise
        """
        key = self.get_cache_key(source)
        return self.cache.get(key)

    def set(self, source: ConfigSource, data: DictConfigT) -> None:
        """Cache data for a source.

        Parameters
        ----------
        source : ConfigSource
            Config source
        data : DictConfigT
            Data to cache
        """
        key = self.get_cache_key(source)
        self.cache[key] = data

    def invalidate(
        self,
        sources: list[Any],
        predicate: Callable[[Any], bool] | None = None,
    ) -> list[int]:
        """Invalidate cache for sources matching predicate or all sources.

        Parameters
        ----------
        sources : list[Any]
            List of all sources to check against
        predicate : Callable[[Any], bool] | None, optional
            Function to select sources to invalidate
            (None = invalidate all), by default None

        Returns
        -------
            List of invalidated cache keys (orders)
        """
        invalidated: list[int] = []

        if predicate is None:
            # Clear all cache
            invalidated = list(self.cache.keys())
            self.cache.clear()
        else:
            # Clear cache for matching sources
            keys_to_remove = []
            for source in sources:
                if predicate(source):
                    key = self.get_cache_key(source)
                    if key in self.cache:
                        keys_to_remove.append(key)

            for key in keys_to_remove:
                del self.cache[key]
                invalidated.append(key)

        return invalidated


# ============================================================================
# ConfigSourceList - Manages Multiple Config Sources
# ============================================================================


class ConfigSourceList(BaseModel):
    """A list of configuration sources with conditional loading.

    ConfigSourceList manages multiple ConfigSource instances, evaluates
    their enable_if conditions, and merges them in order.

    Caching
    -------
    Per-source caching can be enabled with enable_cache(). This caches
    the loaded data for each source independently, which is useful for
    expensive loads (e.g., file I/O, remote APIs). Cache control can be
    granular: specify which sources to cache via names or orders.

    Example:
        >>> sources = ConfigSourceList(data=[
        ...     {"format": "dict", "source": {"base": True}, "order": 0},
        ...     {
        ...         "format": "dict", "source": {"override": True},
        ...         "order": 1, "enable_if": "env == 'dev'"
        ...     }
        ... ])
        >>> config = sources.load(context={"env": "dev"})
        >>> config
        {'base': True, 'override': True}
    """

    model_config = {"frozen": True}

    data: Annotated[
        list[ConfigSource],
        WithJsonSchema({"type": "array", "items": {"type": "object"}}),
    ] = Field(
        description="List of configuration sources",
    )
    name: str | None = Field(
        default=None,
        description="Optional name for this source list",
    )

    # Private: Cache configuration
    _cache_config: CacheConfig = PrivateAttr(default_factory=CacheConfig)

    def __iter__(self) -> Iterator[ConfigSource]:  # type: ignore[override]
        return iter(self.data)

    def __getitem__(self, item: int) -> ConfigSource:
        return self.data[item]

    @model_validator(mode="before")
    @classmethod
    def _validate_arg(cls, arg: Any, info: ValidationInfo) -> dict:
        """Resolve various input formats into ConfigSourceList data dict.

        Handles flexible initialization patterns:
        - ConfigSourceList: Extract data dict
        - None or dict: Single source with order=0
        - Path to file: Single YAML source with order=0
        - Path to directory: Load numbered YAML files (e.g., 00_base.yaml)
        - List: Multiple sources (order auto-assigned if not specified)
        """
        # Already validated ConfigSourceList instance (re-validation)
        if isinstance(arg, ConfigSourceList):
            return {"data": arg.data, "name": arg.name}

        # None or dict -> single dict source
        if arg is None or (isinstance(arg, dict) and "data" not in arg):
            sources = [{"format": "dict", "source": arg or {}, "order": 0}]
            return {"data": sources}

        # Dict with "data" key -> validate it's a list and pass through
        if isinstance(arg, dict) and "data" in arg:
            if not isinstance(arg["data"], list):
                msg = "data must be a sequence"
                raise TypeError(msg)
            return arg

        # Path (string or PathLike)
        if isinstance(arg, str | os.PathLike):
            path = Path(arg)

            # Directory -> load numbered YAML files
            if path.is_dir():
                return cls._resolve_from_dir(path)

            # File -> single YAML source
            sources = [{"format": "yaml", "source": path, "order": 0}]
            return {"data": sources}

        # List -> multiple sources
        if isinstance(arg, list):
            return {"data": arg}

        msg = f"Cannot resolve config sources from type: {type(arg)}"
        raise TypeError(msg)

    @model_validator(mode="after")
    def _validate_order_constraints(self, info: ValidationInfo) -> Self:
        """Validate order constraints from validation context.

        Checks order_min and order_max from validation context if provided.
        This is used by the config_sources() wrapper to enforce constraints.
        """
        if info.context is None:
            return self

        order_max = info.context.get("order_max")
        order_min = info.context.get("order_min")

        if order_max is None and order_min is None:
            return self

        # Validate all sources meet the constraints
        for source in self.data:
            if order_max is not None and source.order > order_max:
                msg = (
                    f"Config source order {source.order} exceeds maximum "
                    f"allowed order {order_max}"
                )
                raise ValueError(msg)
            if order_min is not None and source.order < order_min:
                msg = (
                    f"Config source order {source.order} below minimum "
                    f"allowed order {order_min}"
                )
                raise ValueError(msg)

        return self

    @field_validator("data", mode="before")
    @classmethod
    def _check_data_order_and_sort(  # noqa: C901
        cls,
        data: Any,
        info: ValidationInfo,
    ) -> list:
        """Validate and sort sources by order."""
        if not isinstance(data, collections.abc.Sequence):
            msg = "data must be a sequence"
            raise TypeError(msg)

        # Check if we should auto-assign order based on position
        implicit_order = (info.context or {}).get("config_source_implicit_order", False)
        if implicit_order:
            data = deepcopy(data)
            for i, source in enumerate(data):
                if isinstance(source, dict):
                    source.setdefault("order", i)
                    # Auto-infer format if not set
                    if "format" not in source:
                        src = source.get("source")
                        if isinstance(src, (str, Path)):
                            source["format"] = "yaml"
                        elif isinstance(src, dict):
                            source["format"] = "dict"
                        elif isinstance(src, (list, ConfigSourceList)):
                            source["format"] = "list"

        # Validate orders are unique
        orders = [s.get("order") if isinstance(s, dict) else s.order for s in data]
        if len(set(orders)) != len(orders):
            msg = f"Config source orders must be unique: {orders}"
            raise ValueError(msg)

        # Sort by order
        def get_order(s: Any) -> int:
            if isinstance(s, dict):
                order = s.get("order")
                return order if order is not None else 0
            return s.order

        return sorted(data, key=get_order)

    def _load_source(
        self,
        source: ConfigSource,
        context: dict[str, Any] | None = None,
    ) -> DictConfigT:
        """Load data from a source with optional caching.

        Parameters
        ----------
        source : ConfigSource
            Config source to load
        context : dict[str, Any] | None, optional
            Context dictionary for conditional loading, by default None

        Returns
        -------
        DictConfigT
            Configuration data from the source
        """
        # Check if this source should be cached
        if self._cache_config.should_cache(source):
            # Try to get from cache
            cached_data = self._cache_config.get(source)
            if cached_data is not None:
                logger.debug(
                    f"Source {source.name or '<unnamed>'} (order={source.order}): "
                    f"loaded from cache",
                )
                return cached_data

            # Load and cache
            data = source.load(context=context)
            self._cache_config.set(source, data)
            logger.debug(
                f"Source {source.name or '<unnamed>'} (order={source.order}): "
                f"loaded and cached",
            )
            return data

        # Load without caching
        return source.load(context=context)

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load and merge all enabled configuration sources.

        Sources are evaluated for enable_if conditions, then loaded and
        merged in order (lower order first, higher order overrides).

        If caching is enabled, individual sources may be cached based on
        the cache configuration.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary for evaluating enable_if conditions, by default None

        Returns
        -------
        DictConfigT
            Merged configuration dictionary
        """
        merged: DictConfigT = {}

        for i, source in enumerate(self):
            if not source.enabled:
                logger.debug(f"Source {source.name} (order={source.order}): disabled")
                continue

            if source.is_enabled_for(context=context):
                data = self._load_source(source, context=context)
                rupdate(merged, data)
                status = "enabled"
            else:
                status = "disabled"

            if source.enable_if is not None:
                logger.debug(
                    f"Source {source.name or '<unnamed>'} (order={source.order}, "
                    f"idx={i}): {status} by enable_if='{source.enable_if}' "
                    f"with context={context}",
                )

        return merged

    def enable_cache(
        self,
        predicate: Callable[[ConfigSource], bool] | None = None,
        exclude: Callable[[ConfigSource], bool] | None = None,
    ) -> None:
        """Enable per-source caching for sources matching predicate.

        Caching is applied at the source level, not at the merged config level.
        This allows expensive sources (e.g., file I/O, remote APIs) to be cached
        while keeping mutable dict sources uncached.

        Parameters
        ----------
        predicate : Callable[[ConfigSource], bool] | None, optional
            Function to select sources to cache.
            If None, cache all sources (unless excluded), by default None
        exclude : Callable[[ConfigSource], bool] | None, optional
            Function to select sources to exclude from caching.
            Applied after predicate, by default None

        Example:
            >>> from tollan.config.sources import ConfigSourceList
            >>> sources = ConfigSourceList(data=[
            ...     {"format": "dict", "source": {"a": 1}, "order": 0, "name": "base"},
            ...     {"format": "dict", "source": {"b": 2}, "order": 1, "name": "env"}
            ... ])

            >>> # Cache all except env
            >>> sources.enable_cache(
            ...     exclude=lambda s: s.name == "env"
            ... )

            >>> # Cache only YAML sources
            >>> sources.enable_cache(
            ...     lambda s: isinstance(s, YamlConfigSource)
            ... )

            >>> # Cache sources with specific orders
            >>> sources.enable_cache(lambda s: s.order > 5)

            >>> sources._cache_config.enabled
            True
        """
        self._cache_config.enabled = True
        self._cache_config.cached_predicate = predicate
        self._cache_config.exclude_predicate = exclude

    def invalidate_cache(
        self,
        predicate: Callable[[ConfigSource], bool] | None = None,
    ) -> None:
        """Invalidate cache for sources matching predicate or all sources.

        Parameters
        ----------
        predicate : Callable[[ConfigSource], bool] | None, optional
            Function to select sources to invalidate.
            If None, invalidate all cached sources, by default None

        Example:
            >>> from tollan.config.sources import ConfigSourceList
            >>> sources = ConfigSourceList(data=[
            ...     {"format": "dict", "source": {"a": 1}, "order": 0, "name": "base"},
            ...     {"format": "dict", "source": {"b": 2}, "order": 1, "name": "env"}
            ... ])
            >>> sources.enable_cache()
            >>> _ = sources.load()  # Populate cache

            >>> # Invalidate all
            >>> sources.invalidate_cache()

            >>> # Invalidate specific sources
            >>> sources.invalidate_cache(
            ...     lambda s: s.name == "env"
            ... )
            >>> sources.invalidate_cache(lambda s: s.order > 5)
        """
        invalidated = self._cache_config.invalidate(
            sources=self.data,
            predicate=predicate,
        )

        if invalidated:
            if predicate is None:
                logger.debug("Invalidated all source caches")
            else:
                for key in invalidated:
                    logger.debug(f"Invalidated cache for source key={key}")

    @overload
    def get(
        self,
        predicate: Callable[[ConfigSource], bool],
        *,
        unique: Literal[True] = True,
    ) -> ConfigSource | None: ...

    @overload
    def get(
        self,
        predicate: Callable[[ConfigSource], bool],
        *,
        unique: Literal[False],
    ) -> list[ConfigSource]: ...

    def get(
        self,
        predicate: Callable[[ConfigSource], bool],
        *,
        unique: bool = True,
    ) -> ConfigSource | list[ConfigSource] | None:
        """Get config source(s) using a predicate function.

        Provides maximum flexibility for source selection via predicate function.

        Parameters
        ----------
        predicate : Callable[[ConfigSource], bool]
            Function taking ConfigSource and returning bool
        unique : bool, optional
            If True (default), ensures only one match and returns single
            source. If False, returns list of all matching sources (empty if none),
            by default True

        Returns
        -------
            If unique=True:
                ConfigSource if exactly one match found, None if no match.
            If unique=False:
                list[ConfigSource] with all matches (empty if no matches).

        Raises
        ------
            ValueError: If unique=True and multiple sources match the predicate.

        Examples
        --------
            >>> from tollan.config.sources import ConfigSourceList
            >>> sources = ConfigSourceList(data=[
            ...     {"format": "dict", "source": {"a": 1}, "order": 0, "name": "base"},
            ...     {"format": "dict", "source": {"b": 2}, "order": 1, "name": "env"},
            ...     {"format": "dict", "source": {"c": 3}, "order": 2, "name": "cli"},
            ... ])

            >>> # Unique match (default)
            >>> source = sources.get(lambda s: s.name == "base")
            >>> source.order
            0

            >>> # Multiple matches with unique=False (non-base sources)
            >>> sources_list = sources.get(
            ...     lambda s: s.name in {"env", "cli"}, unique=False
            ... )
            >>> len(sources_list)
            2
            >>> [s.order for s in sources_list]
            [1, 2]

            >>> # All sources
            >>> all_sources = sources.get(lambda s: True, unique=False)
            >>> len(all_sources)
            3
        """
        matches = [s for s in self.data if predicate(s)]

        if not unique:
            return matches

        # unique=True behavior
        if not matches:
            return None
        if len(matches) > 1:
            details = ", ".join(f"order={s.order} name={s.name!r}" for s in matches)
            msg = (
                f"Ambiguous predicate: found {len(matches)} sources ({details}). "
                f"Refine predicate or use unique=False to get all matches."
            )
            raise ValueError(msg)
        return matches[0]

    @classmethod
    def _resolve_from_dir(cls, path: Path) -> dict[str, Any]:
        """Resolve config sources from directory with numbered YAML files.

        Regex matches: 00_name.yaml, 01_name.yml, 99_anything.yaml

        Parameters
        ----------
        path : Path
            Directory path containing numbered YAML files

        Returns
        -------
        dict[str, Any]
            Dict with "data" (list of sources) and "name" (directory path)
        """
        # Regex for directory-based config loading
        pattern = re.compile(r"^(?P<order>\d+)(_.*)?\ya?ml$")

        sources = []
        for p in path.iterdir():
            m = pattern.match(p.name)
            if m is None:
                continue

            sources.append(
                {
                    "format": "yaml",
                    "source": p,
                    "order": int(m.group("order")),
                },
            )

        return {
            "data": sources,
            "name": path.resolve().as_posix(),
        }


# IMPORTANT: Rebuild models after definition due to forward references:
# - ListConfigSource references ConfigSourceList (circular dependency)
# - ConfigSourceList contains ConfigSource union with ListConfigSource
ListConfigSource.model_rebuild()
ConfigSourceList.model_rebuild()


def resolve_config_sources(
    arg: ConfigSourceList | Path | dict | list | None,
    order_max: int | None = None,
    order_min: int | None = None,
) -> ConfigSourceList:
    """Create a ConfigSourceList from various input formats.

    This is a thin wrapper around ConfigSourceList.model_validate() that:
    - Handles flexible input types (Path, dict, list, None)
    - Passes order constraints via validation context
    - Validates order_min/order_max constraints

    Input patterns supported:
    - ConfigSourceList: Return as-is (with order validation)
    - None or dict: Single dict source with order=0
    - Path to file: Single YAML source with order=0
    - Path to directory: Load numbered YAML files (e.g., 00_base.yaml, 01_dev.yaml)
    - List: Multiple sources (order auto-assigned if not specified)

    Parameters
    ----------
    arg : ConfigSourceList | Path | dict | list | None
        Configuration source specification
    order_max : int | None, optional
        Maximum allowed order value for sources, by default None
    order_min : int | None, optional
        Minimum allowed order value for sources, by default None

    Returns
    -------
    ConfigSourceList
        Validated configuration source list

    Raises
    ------
    ValueError
        If any source order violates order_min or order_max constraints

    Examples
    --------
        >>> # From file path
        >>> csl = resolve_config_sources(Path("config.yaml"))

        >>> # From dict
        >>> csl = resolve_config_sources({"key": "value"})

        >>> # From list with order constraints
        >>> csl = resolve_config_sources(
        ...     [{"source": "base.yaml", "order": 0}],
        ...     order_max=100,
        ... )

        >>> # From directory (loads numbered YAML files)
        >>> csl = resolve_config_sources(Path("config_dir"))
    """
    # Build validation context
    context: dict[str, Any] = {"config_source_implicit_order": True}
    if order_max is not None:
        context["order_max"] = order_max
    if order_min is not None:
        context["order_min"] = order_min
    return ConfigSourceList.model_validate(arg, context=context)
