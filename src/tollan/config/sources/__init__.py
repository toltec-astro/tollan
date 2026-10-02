"""Configuration sources for loading config from various formats."""

from __future__ import annotations

import collections.abc
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self, overload

from loguru import logger
from pydantic import (
    BaseModel,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

# Import dict manipulation utility from utils
from ...utils.dict import rupdate

# Import source implementations
from .base import (
    ConfigSourceFormat,
    DictConfigT,  # downstream models use this
    FileConfigSourceBase,
)
from .dict_ import DictConfigSource
from .envfile import ENV_NAMESPACE_DEFAULT, EnvFileConfigSource
from .list_ import ListConfigSource
from .yaml import YamlConfigSource

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pydantic import (
        ValidationInfo,
    )

__all__ = [
    "ENV_NAMESPACE_DEFAULT",
    "ConfigSource",
    "ConfigSourceFormat",
    "ConfigSourceList",
    "DictConfigSource",
    "EnvFileConfigSource",
    "ListConfigSource",
    "YamlConfigSource",
    "resolve_config_sources",
]

#: YAML, dictionary, dotenv, or nested-list source selected by its ``format`` field.
type ConfigSource = Annotated[
    YamlConfigSource | DictConfigSource | EnvFileConfigSource | ListConfigSource,
    Field(discriminator="format"),
]


# ============================================================================
# Directory loading patterns and format detection
# ============================================================================

# Matches any numbered config file: 00_base.yaml, 10_site.env, 99_anything.yml
_DIR_FILE_PATTERN = re.compile(r"^(?P<order>\d+)(_.*)?(?:\.ya?ml|\.env)$")


def _detect_source_format(path: Path) -> ConfigSourceFormat | None:
    """Return the config source format for *path*, or ``None`` if unsupported.

    Detection uses the suffix, with bare ``.env`` also recognized:

    * ``.env``            → ``"envfile"``
    * ``.yaml`` / ``.yml`` → ``"yaml"``
    * anything else       → ``None``
    """
    if path.suffix == ".env" or path.name == ".env":
        return ConfigSourceFormat.envfile
    if path.suffix in (".yaml", ".yml"):
        return ConfigSourceFormat.yaml
    return None


# ============================================================================
# ConfigSourceList - Manages Multiple Config Sources
# ============================================================================


class ConfigSourceList(BaseModel):
    """A list of configuration sources with conditional loading.

    ConfigSourceList manages multiple ConfigSource instances, evaluates
    their enable_if conditions, and merges them in order. Nested lists are
    traversed in their local order and share one accumulated result.

    Caching
    -------
    File sources cache their read-and-parse results by default. Dictionary
    sources return their in-memory data. Conditions and merging run for each
    context. Cache selection and invalidation delegate to the sources.

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

    def __iter__(
        self,
    ) -> Iterator[ConfigSource]:  # ty: ignore[invalid-method-override]
        # Deliberately expose the contained sources instead of BaseModel fields.
        return iter(self.data)

    def __getitem__(self, item: int) -> ConfigSource:
        return self.data[item]

    @model_validator(mode="before")
    @classmethod
    def _validate_arg(cls, arg: Any, info: ValidationInfo) -> dict:
        """Resolve various input formats into ConfigSourceList data dict.

        Handles flexible initialization patterns:

        - ConfigSourceList: Extract data dict
        - None or dict: Single dict source with order=0
        - Path to file: Single source with order=0; format auto-detected from
          extension (``.env`` → envfile, everything else → yaml)
        - Path to directory: Load all numbered files (e.g., ``00_base.yaml``,
          ``10_site.env``) via :meth:`_resolve_from_dir`
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

            # Directory -> load numbered files of any supported format
            if path.is_dir():
                return cls._resolve_from_dir(path)

            # File -> detect format from extension
            fmt = _detect_source_format(path) or "yaml"
            sources = [{"format": fmt, "source": path, "order": 0}]
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
            # Only declaration keys below are changed. Preserve validated sources,
            # nested source caches, and opaque values inside source payloads.
            data = [
                source.copy() if isinstance(source, dict) else source for source in data
            ]
            for i, source in enumerate(data):
                if isinstance(source, dict):
                    source.setdefault("order", i)
                    # Auto-infer format if not set
                    if "format" not in source:
                        src = source.get("source")
                        if isinstance(src, (str, Path)):
                            source["format"] = (
                                _detect_source_format(Path(src)) or "yaml"
                            )
                        elif isinstance(src, dict):
                            source["format"] = "dict"
                        elif isinstance(src, (list, ConfigSourceList)):
                            source["format"] = "list"

                    # Keep the default with YAML sources so it also applies to
                    # includes parsed later. Explicit source choices win.
                    namespace = (info.context or {}).get(
                        "env_namespace", ENV_NAMESPACE_DEFAULT
                    )
                    if source.get("format") == ConfigSourceFormat.envfile:
                        source.setdefault("namespace", namespace)
                    elif source.get("format") == ConfigSourceFormat.yaml:
                        source.setdefault("env_namespace", namespace)

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

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load and merge all enabled configuration sources.

        Sources are evaluated for enable_if conditions, then loaded and
        merged in order (lower order first, higher order overrides). Nested
        lists, including those read from YAML, apply their sources to the same
        result. List patches can therefore update values from preceding groups.

        Each source manages its own cached reads. Conditions and merging run
        on every call, including for nested lists.

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
        for data in self._iter_data(context):
            rupdate(merged, data)
        return merged

    def _iter_data(
        self, context: dict[str, Any] | None = None
    ) -> Iterator[DictConfigT]:
        """Yield enabled mappings in depth-first, locally sorted source order."""
        for i, source in enumerate(self):
            if not source.enabled:
                logger.debug(f"Source {source.name} (order={source.order}): disabled")
                continue

            if source.is_enabled_for(context=context):
                if isinstance(source, ListConfigSource):
                    data = source.source
                elif isinstance(source, FileConfigSourceBase):
                    data = source._load_data(context)
                else:
                    data = source.load(context=context)
                # Keep patches in sequence: merging a subgroup first can discard
                # repeated list operations or replacements of earlier values.
                if isinstance(data, ConfigSourceList):
                    yield from data._iter_data(context)
                else:
                    yield data
                status = "enabled"
            else:
                status = "disabled"

            if source.enable_if is not None:
                logger.debug(
                    f"Source {source.name or '<unnamed>'} (order={source.order}, "
                    f"idx={i}): {status} by enable_if='{source.enable_if}' "
                    f"with context={context}",
                )

    def enable_cache(
        self,
        predicate: Callable[[ConfigSource], bool] | None = None,
        exclude: Callable[[ConfigSource], bool] | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        """Configure read caching for the contained sources.

        Parameters
        ----------
        predicate : callable, optional
            Select sources to cache. By default, select all sources.
        exclude : callable, optional
            Exclude sources from caching, taking precedence over predicate.
        enabled : bool, optional
            Set False to disable caching for all sources.

        Notes
        -----
        Selection applies to this list's immediate sources. A nested list
        forwards its selected state to its contents. Dictionary sources have
        no read cache. Disabling a file source's cache clears its saved read.

        Examples
        --------
        Select cached sources by name, format, or order. These calls configure
        caching without reading the files:

        >>> sources = ConfigSourceList(data=[
        ...     YamlConfigSource(order=0, name="base", source=Path("base.yaml")),
        ...     EnvFileConfigSource(order=1, name="env", source=Path(".env")),
        ... ])
        >>> sources.enable_cache(exclude=lambda s: s.name == "env")
        >>> sources.enable_cache(lambda s: isinstance(s, YamlConfigSource))
        >>> sources.enable_cache(lambda s: s.order == 0)
        >>> sources.enable_cache(enabled=False)  # Read files on every load.
        """
        for source in self:
            selected = (
                enabled
                and (exclude is None or not exclude(source))
                and (predicate is None or predicate(source))
            )
            source.enable_cache(enabled=selected)

    def invalidate_cache(
        self,
        predicate: Callable[[ConfigSource], bool] | None = None,
    ) -> None:
        """Clear cached reads for selected sources, including nested contents.

        Parameters
        ----------
        predicate : callable, optional
            Select immediate sources to invalidate. By default, invalidate all.
            Selecting a nested list invalidates all its contained source reads.

        Examples
        --------
        Refresh a changed file by selecting its source:

        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as directory:
        ...     path = Path(directory) / "base.yaml"
        ...     _ = path.write_text("limit: 10")
        ...     sources = ConfigSourceList(data=[
        ...         YamlConfigSource(order=0, name="base", source=path),
        ...     ])
        ...     print(sources.load()["limit"])
        ...     _ = path.write_text("limit: 20")
        ...     print(sources.load()["limit"])
        ...     sources.invalidate_cache(lambda s: s.name == "base")
        ...     print(sources.load()["limit"])
        10
        10
        20

        Select by order, or clear all source caches:

        >>> sources.invalidate_cache(lambda s: s.order == 0)
        >>> sources.invalidate_cache()
        """
        for source in self:
            if predicate is None or predicate(source):
                source.invalidate_cache()

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
        """Resolve config sources from a directory of numbered files.

        Recognises two formats by file extension:

        * ``*.yaml`` / ``*.yml``  → :class:`YamlConfigSource`
        * ``*.env``               → :class:`EnvFileConfigSource`

        Files must be prefixed with an integer that determines their load order,
        with an optional ``_label`` suffix:

        .. code-block:: text

            00_base.yaml     # loaded first (order=0)
            01_dev.yml       # overrides 00 (order=1)
            10_site.env      # env vars loaded after yaml files (order=10)

        Non-matching files (no numeric prefix, unsupported extension) are
        silently skipped.  Each numeric prefix becomes the source ``order``
        value, so prefixes must be unique across *all* files in the directory
        (a ``00_base.yaml`` and a ``00_default.env`` in the same directory
        would both receive ``order=0`` and fail validation).

        Parameters
        ----------
        path : Path
            Directory to scan.

        Returns
        -------
        dict[str, Any]
            Dict with ``"data"`` (list of source dicts) and ``"name"``
            (resolved directory path), ready for :class:`ConfigSourceList`.
        """
        sources = []
        for p in path.iterdir():
            m = _DIR_FILE_PATTERN.match(p.name)
            if not m:
                continue
            fmt = _detect_source_format(p)
            if fmt is None:
                continue
            sources.append({"format": fmt, "source": p, "order": int(m.group("order"))})
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
    *,
    env_namespace: str | None = ENV_NAMESPACE_DEFAULT,
) -> ConfigSourceList:
    """Create a ConfigSourceList from various input formats.

    This is a thin wrapper around ConfigSourceList.model_validate() that:
    - Handles flexible input types (Path, dict, list, None)
    - Passes order constraints via validation context
    - Validates order_min/order_max constraints

    Input patterns supported:

    - ConfigSourceList: Return as-is (with order validation)
    - None or dict: Single dict source with order=0
    - Path to file: Single source; format auto-detected from extension
      (``.env`` → :class:`EnvFileConfigSource`, else → :class:`YamlConfigSource`)
    - Path to directory: Load numbered files in sort order — ``*.yaml``/``*.yml``
      → :class:`YamlConfigSource`, ``*.env`` → :class:`EnvFileConfigSource`
    - List: Multiple sources (order auto-assigned if not specified)

    Parameters
    ----------
    arg : ConfigSourceList | Path | dict | list | None
        Configuration source specification
    order_max : int | None, optional
        Maximum allowed order value for sources, by default None
    order_min : int | None, optional
        Minimum allowed order value for sources, by default None
    env_namespace : str | None, optional
        Default namespace for dotenv values, including YAML includes. Explicit
        namespaces on source declarations take precedence. None loads at root.

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
    context: dict[str, Any] = {
        "config_source_implicit_order": True,
        "env_namespace": env_namespace,
    }
    if order_max is not None:
        context["order_max"] = order_max
    if order_min is not None:
        context["order_min"] = order_min
    return ConfigSourceList.model_validate(arg, context=context)
