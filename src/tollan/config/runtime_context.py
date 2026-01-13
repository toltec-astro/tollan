"""Runtime context for managing configuration lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, overload

from pydantic import ConfigDict, Field

from ..utils.cli import dict_from_cli_args
from ..utils.dict import rupdate
from ..utils.log import logger, logit
from ..utils.typing import ensure_cls_attr_from_type_args
from .base import FrozenBaseModel
from .runtime_info import RuntimeInfo
from .sources import (
    ConfigSourceList,
    DictConfigSource,
    resolve_config_sources,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from .handler import ConfigHandler
    from .sources import ConfigSource, DictConfigT

__all__ = [
    "RuntimeConfig",
    "RuntimeContext",
]


class RuntimeConfig[RuntimeInfoT: RuntimeInfo = RuntimeInfo](FrozenBaseModel):
    """Base configuration model with runtime info.

    This is the base model for runtime configurations.

    Type Parameters
    ---------------
        RuntimeInfoT: Runtime info model class (subclass of RuntimeInfo)

    Examples
    --------
        >>> # Use default RuntimeConfig
        >>> config = RuntimeConfig.model_validate({
        ...     "database": {"host": "localhost"},
        ...     "runtime_info": {"env": "dev"}
        ... })

        >>> # Subclass for domain-specific config
        >>> class AppConfig(RuntimeConfig[RuntimeInfo]):
        ...     database_url: str
        ...     debug: bool = False
    """

    model_config = ConfigDict(
        extra="allow",  # to store extra items pending validation
    )

    runtime_info: RuntimeInfoT = Field(
        # this get validated to the actual RuntimeInfoT
        default_factory=dict,
        description="Runtime information",
    )  # pyright: ignore[reportAssignmentType]


class RuntimeContext[RuntimeConfigT: RuntimeConfig = RuntimeConfig]:
    """Entry point for runtime-aware configuration management.

    RuntimeContext manages a ConfigSourceList with a four-tier architecture:
    1. Default tier (order=-1) - Base defaults, lowest priority
    2. User sources (order=0+) - From config files/dicts
    3. Info tier (order=1000) - Runtime info dict data
    4. Override tier (order=1001) - Runtime overrides, highest priority

    It provides:
    - Lazy-loaded, cached config model object via `.config` cached property
    - Cached config dict via `.config_dict` cached property
    - Context management for temporary config overrides
    - Registration system for ConfigHandler subclasses
    - Factory methods for common setups (from_cli, etc.)

    Type Parameters
    ---------------
        RuntimeConfigT: Runtime config class (subclass of RuntimeConfig)

    Examples
    --------
        >>> # Basic usage
        >>> rc = RuntimeContext(
        ...     config_sources=[
        ...         {"format": "dict", "source": {"app": "test"}, "order": 0},
        ...         {"format": "dict", "source": {"debug": True}, "order": 1}
        ...     ]
        ... )
        >>> config = rc.config  # Validated RuntimeConfig model
        >>> rc.config_dict['app']
        'test'

        >>> # Temporary context override
        >>> with rc.set_context({"env": "production"}):
        ...     prod_config = rc.config_dict
    """

    # Tier configuration constants
    _USER_ORDER_MIN: ClassVar[int] = 0
    _USER_ORDER_MAX: ClassVar[int] = 999
    TIERS: ClassVar[
        dict[Literal["default", "info", "override"], dict[str, str | int]]
    ] = {
        "default": {"name": "default", "order": _USER_ORDER_MIN - 1},
        "info": {"name": "info", "order": _USER_ORDER_MAX + 1},
        "override": {"name": "override", "order": _USER_ORDER_MAX + 2},
    }
    """Tier configurations with name and order."""

    runtime_config_cls: ClassVar[type[RuntimeConfigT]] = RuntimeConfig  # type: ignore[assignment]

    config_handler_cls_registry: ClassVar[set[type[ConfigHandler]]] = set()
    """Registry of ConfigHandler classes for this RuntimeContext."""

    _config_sources: ConfigSourceList

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Automatically infer runtime_config_cls from RuntimeConfigT type parameter.

        Always infers from the type parameter, ensuring consistency. If you need
        a different RuntimeConfig, specify it in the type parameter:

            class MyContext(RuntimeContext[MyConfig]):
                pass

        Args:
            **kwargs: Additional keyword arguments

        Raises
        ------
            TypeError: If runtime_config_cls is explicitly set (use type param instead)
        """
        super().__init_subclass__(**kwargs)
        ensure_cls_attr_from_type_args(
            cls,
            "runtime_config_cls",
            max_depth=2,
            bound=RuntimeConfig,
            skip_on_exist=False,
        )

    def __init__(
        self,
        config_sources: Path | dict | list | ConfigSourceList | None = None,
    ) -> None:
        # Build four-tier ConfigSourceList with granular caching
        # Default and override tiers are NOT cached (they're mutable)
        # User sources ARE cached (they're typically from immutable files)

        # Create tier sources from TIERS dict
        tier_sources: list[dict[str, Any] | ConfigSource] = [
            tier_config | {"format": "dict", "source": {}, "enabled": True}
            for tier_config in self.TIERS.values()
        ]

        # Add user sources if provided (order=0...N, cached)
        if config_sources is not None:
            user_sources = resolve_config_sources(
                config_sources,
                order_min=self._USER_ORDER_MIN,
                order_max=self._USER_ORDER_MAX,
            )
            logger.debug(f"Loaded {len(user_sources.data)} user config source(s)")
            tier_sources.extend(user_sources.data)

        # Create ConfigSourceList with caching (sources will be sorted by order)
        # Don't cache default, info, and override tiers
        config_source_list = self._config_sources = ConfigSourceList.model_validate(
            tier_sources,
        )
        config_source_list.enable_cache(
            exclude=lambda s: s.name
            in {
                self.TIERS["default"]["name"],
                self.TIERS["info"]["name"],
                self.TIERS["override"]["name"],
            },
        )

        # Inject runtime_info dict into info tier
        # This must happen after _config_sources is set
        info_source = self._get_tier("info")
        info_source.source["runtime_info"] = {
            "config_sources": self._config_sources,
            "validation_context": {},
        }

    @classmethod
    def from_cli(
        cls,
        config_path: Path | None = None,
        env_files: list[Path] | None = None,
        cli_args: list[str] | None = None,
    ) -> RuntimeContext[RuntimeConfigT]:
        """Create RuntimeContext from CLI arguments.

        This factory method creates a standard CLI configuration layout:
        - Config path (file or directory) at order=0
        - Env files at order=100+
        - CLI args converted to overrides env files at order=200

        Parameters
        ----------
        config_path : Path | None, optional
            Main config file or directory path. If directory,
            loads numbered YAML files (e.g., 00_base.yaml, 01_dev.yaml),
            by default None
        env_files : list[Path] | None, optional
            List of .env file paths, by default None
        cli_args : list[str] | None, optional
            CLI arguments in "--key=value" or "--key value" format.
            Converted to nested dict (e.g., ["--db.host", "localhost"] →
            {"db": {"host": "localhost"}}), by default None

        Returns
        -------
        RuntimeContext[RuntimeConfigT]
            RuntimeContext instance configured for CLI usage

        Example:
            >>> from pathlib import Path
            >>> # Create from CLI args
            >>> rc = RuntimeContext.from_cli(
            ...     cli_args=["--debug", "true", "--port", "8080"]
            ... )
            >>> 'debug' in rc.config_dict
            True
        """
        sources = []

        n_override_orders_max = 100
        env_file_base_order = cls._USER_ORDER_MAX - n_override_orders_max
        # Add main config path (file or directory)
        if config_path is not None:
            with logit(logger.debug, f"Loading config from path: {config_path}"):
                # config_sources handles both files and directories
                config_source_list = resolve_config_sources(
                    config_path,
                    order_min=cls._USER_ORDER_MIN,
                    order_max=env_file_base_order - 1,
                )
            sources.extend(config_source_list.data)

        # Add env files
        if env_files:
            if len(env_files) > n_override_orders_max - 1:
                msg = "Too many env files."
                raise ValueError(msg)
            for i, env_file in enumerate(env_files):
                sources.append(
                    {
                        "format": "envfile",
                        "source": env_file,
                        "order": env_file_base_order + i,
                    },
                )

        # Parse and add CLI args as overrides
        if cli_args:
            cli_overrides = dict_from_cli_args(cli_args)
            sources.append(
                {
                    "format": "dict",
                    "source": cli_overrides,
                    "order": cls._USER_ORDER_MAX,
                    "name": "cli_overrides",
                },
            )

        return cls(config_sources=sources if sources else None)

    @classmethod
    def register_config_handler_cls(
        cls,
        config_handler_cls: type[ConfigHandler],
    ) -> None:
        """Register a ConfigHandler class.

        Types registered can be instantiated via the `__getitem__` interface.

        Parameters
        ----------
        config_handler_cls : type[ConfigHandler]
            ConfigHandler subclass to register
        """
        cls.config_handler_cls_registry.add(config_handler_cls)

    @overload
    def __getitem__[T: ConfigHandler](
        self,
        config_handler_cls: type[T],
    ) -> T: ...

    @overload
    def __getitem__[T0: ConfigHandler](
        self,
        config_handler_cls: tuple[type[T0]],
    ) -> tuple[T0]: ...

    @overload
    def __getitem__[T0: ConfigHandler, T1: ConfigHandler](
        self,
        config_handler_cls: tuple[type[T0], type[T1]],
    ) -> tuple[T0, T1]: ...

    @overload
    def __getitem__[T0: ConfigHandler, T1: ConfigHandler, T2: ConfigHandler](
        self,
        config_handler_cls: tuple[type[T0], type[T1], type[T2]],
    ) -> tuple[T0, T1, T2]: ...

    @overload
    def __getitem__[
        T0: ConfigHandler,
        T1: ConfigHandler,
        T2: ConfigHandler,
        T3: ConfigHandler,
    ](
        self,
        config_handler_cls: tuple[type[T0], type[T1], type[T2], type[T3]],
    ) -> tuple[T0, T1, T2, T3]: ...

    @overload
    def __getitem__[
        Ts: ConfigHandler,
    ](
        self,
        config_handler_cls: tuple[Ts, ...],
    ) -> tuple[Ts, ...]: ...

    def __getitem__(
        self,
        config_handler_cls,
    ):
        """Get config handler instance(s) configured by this runtime context.

        Args:
            config_handler_cls: ConfigHandler class or tuple of classes

        Returns
        -------
            ConfigHandler instance or tuple of instances

        Raises
        ------
            TypeError: If class is not a ConfigHandler or not registered

        Example:
            >>> from tollan.config import ConfigHandler
            >>> # Assuming MyConfigHandler is registered
            >>> # handler = rc[MyConfigHandler]
            >>> # handlers = rc[Handler1, Handler2, Handler3]
            ... # doctest: +SKIP
        """
        if isinstance(config_handler_cls, tuple):
            return tuple(self.__getitem__(cls) for cls in config_handler_cls)

        # avoid circular import
        from .handler import ConfigHandler  # noqa: PLC0415

        if not issubclass(config_handler_cls, ConfigHandler):
            msg = f"{config_handler_cls} is not a config handler class."
            raise TypeError(msg)

        if config_handler_cls not in self.config_handler_cls_registry:
            msg = f"{config_handler_cls} is not registered to the runtime context."
            raise TypeError(
                msg,
            )

        return config_handler_cls(self)

    @property
    def config_sources(self) -> ConfigSourceList:
        """Get the ConfigSourceList.

        This is the underlying source list that can be used to access
        individual sources, inspect the configuration pipeline, or
        load configuration with different contexts.

        Returns
        -------
            ConfigSourceList instance
        """
        return self._config_sources

    @cached_property
    def config_dict(self) -> DictConfigT:
        """Get the loaded and merged configuration as a dictionary.

        This loads config with the current context and caches the result.
        Cache is invalidated when context changes or when update_*_config
        methods are called.

        Returns
        -------
            Merged configuration dictionary (DictConfigT)
        """
        # Get context from info tier's validation_context dict
        context = self._get_validation_context()
        return self._config_sources.load(context=context or None)

    @cached_property
    def config(self) -> RuntimeConfigT:
        """Get the validated configuration model.

        This validates the merged config dict using the RuntimeConfig model
        (or a subclass defined in runtime_config_cls). The result is cached.

        Returns
        -------
            Validated RuntimeConfig instance
        """
        return self.runtime_config_cls.model_validate(self.config_dict)

    @property
    def runtime_info(self) -> RuntimeInfo:
        """Get runtime info from the validated config.

        Returns
        -------
            Runtime info instance from config.runtime_info
        """
        return self.config.runtime_info

    @contextmanager
    def set_context(
        self,
        context: dict[str, Any],
    ) -> Generator[None]:
        """Context manager to temporarily override validation context.

        This is useful for testing different scenarios or loading config
        under different runtime conditions without permanent changes.

        Parameters
        ----------
        context : dict[str, Any]
            Context dictionary for enable_if expressions. Values are
            merged with existing context (doesn't replace entirely).

        Yields
        ------
        None
            Context is set for duration of with block

        Example:
            >>> rc = RuntimeContext(
            ...     config_sources=[
            ...         {"format": "dict", "source": {"app": "test"}, "order": 0}
            ...     ]
            ... )
            >>> with rc.set_context({"env": "production"}):
            ...     config = rc.config_dict
            >>> rc.config_dict['app']
            'test'
        """
        # Get validation_context dict from info tier
        validation_context = self._get_validation_context()

        # Save previous context
        previous_context = validation_context.copy()

        # Save cached properties by invalidating (returns saved cache)
        saved_cache = self._invalidate_config_cache()

        try:
            # Update context (merge, don't replace)
            validation_context.update(context)
            logger.debug(f"Set config context: {context}")
            yield
        finally:
            # Restore previous context
            validation_context.clear()
            validation_context.update(previous_context)
            logger.debug("Config context cleared")

            # Invalidate caches and restore saved values
            self._invalidate_config_cache()
            for attr, value in saved_cache.items():
                self.__dict__[attr] = value

    def set_config(
        self,
        cfg: DictConfigT,
        tier: Literal["default", "override"],
    ) -> None:
        """Replace a named tier's configuration entirely.

        Parameters
        ----------
        cfg : DictConfigT
            New configuration for the tier
        tier : Literal["default", "override"]
            Tier to set ("default" or "override")
        """
        if tier not in {"default", "override"}:
            msg = "Invalid update tier"
            raise ValueError(msg)
        tier_source = self._get_tier(tier)
        tier_source.source.clear()
        tier_source.source.update(cfg)
        self._invalidate_config_cache()

    def update_config(
        self,
        cfg: DictConfigT,
        tier: Literal["default", "override"],
    ) -> None:
        """Merge configuration into a named tier.

        Parameters
        ----------
        cfg : DictConfigT
            Configuration to merge into the tier
        tier : Literal["default", "override"]
            Tier to update ("default" or "override")
        """
        if tier not in {"default", "override"}:
            msg = "Invalid update tier"
            raise ValueError(msg)
        tier_source = self._get_tier(tier)
        rupdate(tier_source.source, cfg)
        self._invalidate_config_cache()

    def set_default_config(self, cfg: DictConfigT) -> None:
        """Set default configuration (order=-1 tier).

        This only invalidates RuntimeContext caches, not ConfigSourceList
        source caches (since default tier is not cached in sources).

        Parameters
        ----------
        cfg : DictConfigT
            New default configuration
        """
        self.set_config(cfg, tier="default")

    def set_override_config(self, cfg: DictConfigT) -> None:
        """Set override configuration (order=1001 tier).

        This only invalidates RuntimeContext caches, not ConfigSourceList
        source caches (since override tier is not cached in sources).

        Parameters
        ----------
        cfg : DictConfigT
            New override configuration
        """
        self.set_config(cfg, tier="override")

    def update_default_config(self, cfg: DictConfigT) -> None:
        """Merge default configuration (order=-1 tier).

        This only invalidates RuntimeContext caches, not ConfigSourceList
        source caches (since default tier is not cached in sources).

        Parameters
        ----------
        cfg : DictConfigT
            Configuration to merge into default tier
        """
        self.update_config(cfg, tier="default")

    def update_override_config(self, cfg: DictConfigT) -> None:
        """Merge override configuration (order=1001 tier).

        This only invalidates RuntimeContext caches, not ConfigSourceList
        source caches (since override tier is not cached in sources).

        Parameters
        ----------
        cfg : DictConfigT
            Configuration to merge into override tier
        """
        self.update_config(cfg, tier="override")

    def reload(self) -> dict[str | int, Any]:
        """Reload configuration, invalidating all caches.

        This forces a full reload of all config sources, including file-based
        sources that are normally cached.

        Returns
        -------
            Reloaded configuration dictionary
        """
        # Invalidate ConfigSourceList cache
        self.config_sources.invalidate_cache()

        # Invalidate RuntimeContext caches
        self._invalidate_config_cache()

        # Return fresh config
        return self.config_dict

    def _get_tier(
        self,
        tier_name: Literal["default", "override", "info"],
    ) -> DictConfigSource:
        """Get a named tier as a DictConfigSource.

        Args:
            tier_name: Name of tier to get ("default", "override", or "info")

        Returns
        -------
            Named tier as DictConfigSource
        """
        tier_config = self.TIERS[tier_name]
        tier = self._config_sources.get(lambda s: s.name == tier_config["name"])
        assert tier is not None, f"{tier_name.capitalize()} tier must exist"
        assert isinstance(tier, DictConfigSource), (
            f"{tier_name.capitalize()} tier must be DictConfigSource"
        )
        return tier

    def _get_validation_context(self) -> dict[str, Any]:
        """Get the validation_context dict from info tier.

        The validation_context dict is guaranteed to exist because it's
        created during initialization by _inject_runtime_state().

        Returns
        -------
            The validation_context dict that can be mutated
        """
        info_tier = self._get_tier("info")
        runtime_info_dict = info_tier.source["runtime_info"]
        return runtime_info_dict["validation_context"]

    def _invalidate_config_cache(self) -> dict[str, Any]:
        """Invalidate RuntimeContext config caches.

        This clears the cached_property values for config_dict and config,
        forcing them to be recomputed on next access.

        Returns
        -------
            Dictionary of invalidated cache entries {attr_name: value}
            that can be used to restore the cache later
        """
        # Save and clear cached properties
        saved_cache = {}
        for attr in ["config_dict", "config"]:
            if attr in self.__dict__:
                saved_cache[attr] = self.__dict__[attr]
                del self.__dict__[attr]
                logger.debug(f"{attr} cache invalidated")
        return saved_cache
