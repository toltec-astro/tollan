"""Runtime context for managing configuration lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, cast, overload

from pydantic import ConfigDict, Field

from ..utils.cli import dict_from_cli_args
from ..utils.dict import rupdate
from ..utils.log import logger, logit
from ..utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)
from .base import FrozenBaseModel
from .runtime_info import RuntimeInfo
from .sources import (
    ENV_NAMESPACE_DEFAULT,
    ConfigSourceFormat,
    ConfigSourceList,
    DictConfigSource,
    ListConfigSource,
    resolve_config_sources,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator
    from pathlib import Path

    import typer

    from .env import EnvHandler
    from .handler import ConfigHandler
    from .sources import ConfigSource, DictConfigT

__all__ = [
    "RuntimeConfig",
    "RuntimeContext",
]


class RuntimeConfig[RuntimeInfoT: RuntimeInfo = RuntimeInfo](FrozenBaseModel):
    """Base configuration model with runtime info.

    This is the base model for runtime configurations.

    Notes
    -----
    Bind ``RuntimeInfoT`` to the RuntimeInfo subclass used for runtime
    information. Defaults to RuntimeInfo.

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

    Load and validate settings lazily, in increasing priority:

    1. Defaults (order -1).
    2. User files and dictionaries (orders 0 through 999).
    3. Runtime information (order 1000).
    4. Explicit overrides (order 1001).

    Use ``config_dict`` for merged values, ``config`` for the validated model,
    and ``with_config()`` to create a runtime with patched settings.
    Existing handlers retain their validated settings when this runtime changes.

    Parameters
    ----------
    config_sources : pathlib.Path, dict, list, or ConfigSourceList, optional
        Source declarations, a configuration file/directory, or a resolved
        source list. None creates a runtime with no user sources. Explicit
        top-level source orders must be between 0 and 999, inclusive.

    Notes
    -----
    Bind ``RuntimeConfigT`` to the configuration model to validate.
    Defaults to RuntimeConfig.

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

    # Replaced on concrete subclasses by __init_subclass__; runtime type:
    # type[RuntimeConfigT].
    runtime_config_cls: ClassVar = RuntimeConfig

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
        bindings = resolve_concrete_generic_bindings(
            cls,
            RuntimeContext,
            RuntimeConfigT=GenericBindingRequirement(
                "runtime_config_cls",
                RuntimeConfig,
            ),
        )
        if bindings is not None:
            cls.runtime_config_cls = bindings["RuntimeConfigT"]

    def __init__(
        self,
        config_sources: Path | dict | list | ConfigSourceList | None = None,
    ) -> None:
        # Create tier sources from TIERS dict
        tier_sources: list[dict[str, Any] | ConfigSource] = [
            tier_config | {"format": "dict", "source": {}, "enabled": True}
            for tier_config in self.TIERS.values()
        ]

        # Add user sources if provided (order=0...N)
        if config_sources is not None:
            user_sources = resolve_config_sources(
                config_sources,
                order_min=self._USER_ORDER_MIN,
                order_max=self._USER_ORDER_MAX,
            )
            logger.debug(f"Loaded {len(user_sources.data)} user config source(s)")
            tier_sources.extend(user_sources.data)

        self._config_sources = ConfigSourceList.model_validate(tier_sources)

        # Inject runtime_info dict into info tier
        # This must happen after _config_sources is set
        info_source = self._get_tier("info")
        info_source.source["runtime_info"] = {
            "config_sources": self._config_sources,
            "validation_context": {},
        }

    @classmethod
    def add_cli_options(cls) -> Callable:
        """Add configuration path options to a Tollan command or group callback.

        Apply below ``@app.command()`` or ``@app.callback()``. The decorator
        adds ``--config_paths`` (``-c``) and ``--env_paths``; both accept several
        paths or repeated occurrences. Files and directories must exist.

        Use :meth:`from_cli_ctx` inside the callback to construct a runtime.
        The decorator does not load configuration or change ``ctx.obj``.

        Examples
        --------
        >>> import typer
        >>> from tollan.utils.typer import TollanTyper
        >>> app = TollanTyper()
        >>> @app.command()
        ... @RuntimeContext.add_cli_options()
        ... def show(ctx: typer.Context):
        ...     rc = RuntimeContext.from_cli_ctx(ctx)
        ...     print(rc.config_dict.get("search"))
        >>> # app --config_paths settings.yaml --env_paths local.env
        """
        from .cli import _add_cli_options  # noqa: PLC0415

        return _add_cli_options

    @classmethod
    @overload
    def from_cli_ctx(
        cls,
        ctx: typer.Context,
        *,
        return_env_handler: Literal[False] = False,
        **kwargs: Any,
    ) -> Self: ...

    @classmethod
    @overload
    def from_cli_ctx(
        cls,
        ctx: typer.Context,
        *,
        return_env_handler: Literal[True],
        **kwargs: Any,
    ) -> tuple[Self, EnvHandler | None]: ...

    @classmethod
    @overload
    def from_cli_ctx(
        cls,
        ctx: typer.Context,
        *,
        return_env_handler: bool,
        **kwargs: Any,
    ) -> Self | tuple[Self, EnvHandler | None]: ...

    @classmethod
    def from_cli_ctx(
        cls,
        ctx: typer.Context,
        *,
        return_env_handler: bool = False,
        **kwargs: Any,
    ) -> Self | tuple[Self, EnvHandler | None]:
        """Create a runtime from the current callback's configuration path options.

        Parameters
        ----------
        ctx : typer.Context
            Context of a command or group callback decorated with
            :meth:`add_cli_options`.
        return_env_handler : bool, optional
            Return ``(runtime, env_handler)`` instead of just the runtime.
            See :meth:`from_cli` for the handler's loading and namespace behavior.
        **kwargs
            Additional :meth:`from_cli` arguments, such as ``config_formats``,
            ``env_namespace``, and explicitly supplied ``cli_args``. Path
            arguments come from the context and must not be passed again.

        Returns
        -------
        RuntimeContext or tuple[RuntimeContext, EnvHandler | None]
            A new runtime created by this class's ``from_cli`` method. The caller
            chooses whether to store it on ``ctx.obj`` or elsewhere. When
            requested, the second item is the environment handler, or None
            when ``env_namespace=None``.

        Examples
        --------
        Within a decorated callback::

            rc = RuntimeContext.from_cli_ctx(ctx, env_namespace="process")

        To accept configuration overrides, configure argument handling on the
        application and pass the selected arguments explicitly as ``cli_args``.
        Unconsumed arguments in ``ctx.args`` are not read automatically.
        """
        return cls.from_cli(
            config_paths=ctx.params["config_paths"],
            env_paths=ctx.params["env_paths"],
            return_env_handler=return_env_handler,
            **kwargs,
        )

    @classmethod
    @overload
    def from_cli(
        cls,
        config_paths: list[Path] | None = None,
        env_paths: list[Path] | None = None,
        cli_args: list[str] | None = None,
        *,
        config_formats: Collection[ConfigSourceFormat] | None = None,
        env_namespace: str | None = ENV_NAMESPACE_DEFAULT,
        return_env_handler: Literal[False] = False,
    ) -> Self: ...

    @classmethod
    @overload
    def from_cli(
        cls,
        config_paths: list[Path] | None = None,
        env_paths: list[Path] | None = None,
        cli_args: list[str] | None = None,
        *,
        config_formats: Collection[ConfigSourceFormat] | None = None,
        env_namespace: str | None = ENV_NAMESPACE_DEFAULT,
        return_env_handler: Literal[True],
    ) -> tuple[Self, EnvHandler | None]: ...

    @classmethod
    @overload
    def from_cli(
        cls,
        config_paths: list[Path] | None = None,
        env_paths: list[Path] | None = None,
        cli_args: list[str] | None = None,
        *,
        config_formats: Collection[ConfigSourceFormat] | None = None,
        env_namespace: str | None = ENV_NAMESPACE_DEFAULT,
        return_env_handler: bool,
    ) -> Self | tuple[Self, EnvHandler | None]: ...

    @classmethod
    def from_cli(  # noqa: PLR0913 -- independent CLI source and return options
        cls,
        config_paths: list[Path] | None = None,
        env_paths: list[Path] | None = None,
        cli_args: list[str] | None = None,
        *,
        config_formats: Collection[ConfigSourceFormat] | None = None,
        env_namespace: str | None = ENV_NAMESPACE_DEFAULT,
        return_env_handler: bool = False,
    ) -> Self | tuple[Self, EnvHandler | None]:
        """Create a runtime from ordered config files, env files, and CLI overrides.

        Later paths override earlier paths. Environment paths override config
        paths, and CLI arguments override both.

        Parameters
        ----------
        config_paths : list[Path] | None, optional
            Config files or directories, in increasing precedence. Each directory
            loads numbered YAML and dotenv files in local numeric order. YAML
            files may contain mappings or conditional source lists.
        env_paths : list[Path] | None, optional
            Dotenv files or directories, in increasing precedence. Each directory
            loads numbered env files in local numeric order; non-env entries are
            skipped. Values remain strings under ``env_namespace``.
            Loading does not modify the process environment.
        cli_args : list[str] | None, optional
            CLI arguments in "--key=value" or "--key value" format.
            Converted to nested dict (e.g., ["--db.host", "localhost"] →
            {"db": {"host": "localhost"}}), by default None
        config_formats : Collection[ConfigSourceFormat] | None, optional
            Formats to accept from ``config_paths``. None accepts all supported
            formats; an empty collection accepts none. Explicit includes inside
            YAML source lists are not filtered.
        env_namespace : str | None, optional
            Default key for dotenv values; defaults to ``ENV_NAMESPACE_DEFAULT``.
            None loads at the root. Applies to both path options and included
            sources, unless a source explicitly declares its own namespace.
        return_env_handler : bool, optional
            If True, also return a handler capturing the merged environment
            namespace. This loads the runtime configuration and validates the
            environment mapping immediately. If ``env_namespace=None``, return
            None in place of the handler and leave loading lazy. Defaults to
            False, returning only the lazily loaded runtime.

        Returns
        -------
        RuntimeContext or tuple[RuntimeContext, EnvHandler | None]
            Configured runtime, with an environment handler when requested.
            A missing namespace produces an empty handler. Sources explicitly
            using other namespaces are not collected into this handler.
            No process environment variables are changed.

        Example:
            >>> from pathlib import Path
            >>> # Create from CLI args
            >>> rc = RuntimeContext.from_cli(
            ...     cli_args=["--debug", "true", "--port", "8080"]
            ... )
            >>> 'debug' in rc.config_dict
            True
        """
        if config_formats is not None:
            config_formats = frozenset(ConfigSourceFormat(f) for f in config_formats)
        sources: list[ConfigSource] = []
        for order, (name, paths, formats) in enumerate(
            [
                (
                    "config_paths",
                    config_paths,
                    config_formats,
                ),
                ("env_paths", env_paths, {ConfigSourceFormat.envfile}),
            ]
        ):
            if not paths:
                continue
            groups = []
            for i, path in enumerate(paths):
                with logit(logger.debug, f"Loading {name} from path: {path}"):
                    resolved = resolve_config_sources(path, env_namespace=env_namespace)
                filtered = []
                for source in resolved:
                    if formats is None or source.format in formats:
                        filtered.append(source)
                    else:
                        logger.debug(
                            "{}: skipping {} source {}",
                            name,
                            source.format,
                            source.name,
                        )
                # Each path has a local order space; later paths override the
                # whole preceding group without renumbering its file sources.
                groups.append(
                    ListConfigSource(
                        order=i,
                        name=str(path),
                        source=ConfigSourceList(data=filtered, name=resolved.name),
                    )
                )
            sources.append(
                ListConfigSource(
                    order=order, name=name, source=ConfigSourceList(data=groups)
                )
            )

        # Parse and add CLI args as overrides
        if cli_args:
            cli_overrides = dict_from_cli_args(cli_args)
            sources.append(
                DictConfigSource(order=2, name="cli_overrides", source=cli_overrides),
            )

        runtime = cls(config_sources=sources or None)
        if not return_env_handler:
            return runtime
        if env_namespace is None:
            return runtime, None
        from .env import _make_env_handler  # noqa: PLC0415

        return runtime, _make_env_handler(runtime, env_namespace)

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
        """Ordered configuration source list.

        This is the underlying source list that can be used to access
        individual sources, inspect the configuration pipeline, or
        load configuration with different contexts.

        Returns
        -------
        ConfigSourceList
            Sources available for inspection or loading with a selected context.
        """
        return self._config_sources

    @cached_property
    def config_dict(self) -> DictConfigT:
        """Loaded and merged configuration dictionary.

        This loads config with the current context and caches the result.
        Cache is invalidated when context changes or when update_*_config
        methods are called.

        Returns
        -------
        DictConfigT
            Cached merged values. Treat nested data as read-only and use the
            runtime's update methods to change settings.
        """
        # Get context from info tier's validation_context dict
        context = self._get_validation_context()
        return self._config_sources.load(context=context or None)

    @cached_property
    def config(self) -> RuntimeConfigT:
        """Validated configuration model for the current settings.

        This validates the merged config dict using the RuntimeConfig model
        (or a subclass defined in runtime_config_cls). The result is cached.

        Returns
        -------
        RuntimeConfig
            Cached instance of the configured runtime model class.
        """
        runtime_config_cls = cast(
            "type[RuntimeConfigT]",
            self.runtime_config_cls,
        )
        return runtime_config_cls.model_validate(
            self.config_dict, context=self._get_validation_context()
        )

    @property
    def runtime_info(self) -> RuntimeInfo:
        """Runtime information from the validated configuration.

        Returns
        -------
        RuntimeInfo
            The current model's runtime_info value.
        """
        return self.config.runtime_info

    def with_config(
        self,
        *,
        defaults: DictConfigT | None = None,
        overrides: DictConfigT | None = None,
        validation_context: dict[str, Any] | None = None,
    ) -> Self:
        """Create a runtime with patched defaults, overrides, and context.

        Parameters
        ----------
        defaults, overrides : dict, optional
            Settings to merge into copies of the current default and override
            tiers. User sources retain their existing precedence.
        validation_context : dict, optional
            Values to merge into a copy of the current validation context.

        Returns
        -------
        Self
            New instance of the same runtime class with independently updatable
            tiers and validation context.

        Notes
        -----
        User-source objects and their cached file reads are shared. Updating
        tiers through either runtime's API does not change the other runtime.
        Direct mutation of shared source data is not isolated.

        Examples
        --------
        >>> rc = RuntimeContext()
        >>> other = rc.with_config(overrides={"port": 9000})
        >>> other.config_dict["port"]
        9000
        >>> "port" in rc.config_dict
        False
        """
        variant = type(self)(
            config_sources=[
                source
                for source in self.config_sources
                if self._USER_ORDER_MIN <= source.order <= self._USER_ORDER_MAX
            ]
        )
        for tier in ("default", "override", "info"):
            rupdate(variant._get_tier(tier).source, self._get_tier(tier).source)
        variant._get_tier("info").source["runtime_info"]["config_sources"] = (
            variant.config_sources
        )
        if defaults is not None:
            variant.update_default_config(defaults)
        if overrides is not None:
            variant.update_override_config(overrides)
        if validation_context is not None:
            rupdate(variant._get_validation_context(), validation_context)
        variant._invalidate_config_cache()
        return variant

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

        This invalidates RuntimeContext caches. Dictionary tiers have no
        separate read cache.

        Parameters
        ----------
        cfg : DictConfigT
            New default configuration
        """
        self.set_config(cfg, tier="default")

    def set_override_config(self, cfg: DictConfigT) -> None:
        """Replace the highest-priority override configuration.

        This invalidates RuntimeContext caches. Dictionary tiers have no
        separate read cache.

        Parameters
        ----------
        cfg : DictConfigT
            New override configuration
        """
        self.set_config(cfg, tier="override")

    def update_default_config(self, cfg: DictConfigT) -> None:
        """Merge default configuration (order=-1 tier).

        This invalidates RuntimeContext caches. Dictionary tiers have no
        separate read cache.

        Parameters
        ----------
        cfg : DictConfigT
            Configuration to merge into default tier
        """
        self.update_config(cfg, tier="default")

    def update_override_config(self, cfg: DictConfigT) -> None:
        """Merge values into the highest-priority override configuration.

        This invalidates RuntimeContext caches. Dictionary tiers have no
        separate read cache.

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
        DictConfigT
            Newly loaded and merged settings. Existing handlers and other
            runtimes' loaded configurations are unchanged.
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
