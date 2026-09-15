"""Configuration handler classes for domain-specific config management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    LiteralString,
    Self,
    cast,
    get_args,
    get_origin,
)

from pydantic import BaseModel

from ..utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)
from .runtime_context import RuntimeContext

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .runtime_context import RuntimeConfig
    from .runtime_info import RuntimeInfo
    from .sources import DictConfigT

__all__ = [
    "ConfigHandler",
    "SubConfigKeyTransformer",
]


class ConfigHandler[
    ConfigModelT: BaseModel,
    RuntimeContextT: RuntimeContext = RuntimeContext,
]:
    """Base class for domain-specific configuration handlers.

    Extracts and validates a domain configuration when constructed. The validated
    model is available as `config`, and its execution context as `runtime_info`.
    Use ordinary `functools.cached_property` for resources built from the config.

    Type Parameters
    ---------------
    ConfigModelT
        Pydantic model used to validate the domain configuration.
    RuntimeContextT
        Accepted runtime context type; defaults to RuntimeContext.

    Notes
    -----
    Subclasses implement `prepare_config_data` to extract their domain and
    `prepare_runtime_config_data` to wrap domain patches for temporary variants.
    `SubConfigKeyTransformer` supplies both methods for a single runtime key.

    Examples
    --------
    Define a handler that reads a database section and caches a derived resource:

        >>> from functools import cached_property
        >>> from pydantic import BaseModel
        >>> from tollan.config import ConfigHandler, RuntimeContext
        >>>
        >>> class MyConfigModel(BaseModel):
        ...     database_url: str
        ...     max_connections: int = 10
        >>>
        >>> class MyConfigHandler(ConfigHandler[MyConfigModel]):
        ...     @classmethod
        ...     def prepare_config_data(cls, runtime_config):
        ...         return runtime_config.database
        ...     @classmethod
        ...     def prepare_runtime_config_data(cls, config_data):
        ...         return {"database": config_data}
        ...     @cached_property
        ...     def connection_options(self):
        ...         return {"url": self.config.database_url}
        >>>
        >>> rc = RuntimeContext()
        >>> rc.update_default_config({
        ...     "database": {"database_url": "postgresql://localhost/db"}
        ... })
        >>> handler = MyConfigHandler(rc)
        >>> handler.config.database_url
        'postgresql://localhost/db'
        >>> handler.connection_options is handler.connection_options
        True
        >>> with handler.temporary_config(overrides={"max_connections": 20}) as other:
        ...     print(other.config.max_connections)
        ...     print(other.connection_options is handler.connection_options)
        20
        False
        >>> handler.config.max_connections
        10
    """

    # Set on concrete subclasses by __init_subclass__; runtime type:
    # type[ConfigModelT].
    config_model_cls: ClassVar
    _rc: RuntimeContextT
    _config: ConfigModelT
    _runtime_info: RuntimeInfo

    def __init__(self, runtime_context: RuntimeContextT) -> None:
        """Initialize and validate a domain handler.

        Parameters
        ----------
        runtime_context : RuntimeContext
            Runtime providing the domain settings and validation context.

        Raises
        ------
        pydantic.ValidationError
            If the runtime or extracted domain settings fail validation.
        """
        self._rc = runtime_context
        self._load_config()

    def __init_subclass__(cls, **kwargs):
        """Register subclass and derive config_model_cls from its bound type.

        This automatically:
        - Extracts ConfigModelT from Generic[ConfigModelT]
        - Registers the handler class with RuntimeContext
        """
        super().__init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            ConfigHandler,
            ConfigModelT=GenericBindingRequirement(
                "config_model_cls",
                BaseModel,
            ),
        )
        if bindings is None:
            return
        cls.config_model_cls = bindings["ConfigModelT"]
        # Register with RuntimeContext (avoid circular import)
        from .runtime_context import RuntimeContext  # noqa: PLC0415

        RuntimeContext.register_config_handler_cls(cls)

    @property
    def config(self) -> ConfigModelT:
        """Return the validated domain configuration.

        Returns
        -------
        ConfigModelT
            Model created during initialization. Runtime updates do not replace
            it; use `recreate` to construct a handler with current settings.
        """
        return self._config

    @property
    def runtime_info(self) -> RuntimeInfo:
        """Return the runtime information used to validate this handler.

        Returns
        -------
        RuntimeInfo
            Execution metadata and validation context captured at construction.

        Notes
        -----
        Treat the model as read-only. Later runtime updates do not replace it,
        but `config_sources` remains a shared reference for source introspection.
        """
        return self._runtime_info

    @classmethod
    def prepare_config_data(cls, runtime_config: RuntimeConfig) -> dict:
        """Prepare config data from runtime config.

        Subclasses must implement this to extract their specific config
        from the runtime config model.

        Parameters
        ----------
        runtime_config : RuntimeConfig
            RuntimeConfig model instance

        Returns
        -------
        dict
            Config data dict for validation

        Raises
        ------
        NotImplementedError
            If not overridden by subclass
        """
        msg = f"{cls.__name__} must implement prepare_config_data()"
        raise NotImplementedError(
            msg,
        )

    @classmethod
    def prepare_runtime_config_data(cls, config_data: DictConfigT) -> DictConfigT:
        """Prepare runtime config data from config data.

        Subclasses must implement this to wrap their config data
        for updating the runtime config.

        Parameters
        ----------
        config_data : DictConfigT
            Domain config data

        Returns
        -------
        DictConfigT
            Runtime config data dict

        Raises
        ------
        NotImplementedError
            If not overridden by subclass
        """
        msg = f"{cls.__name__} must implement prepare_runtime_config_data()"
        raise NotImplementedError(
            msg,
        )

    def _load_config(self) -> None:
        """Initialize `_config` and `_runtime_info` from the attached runtime.

        Extract domain settings with `prepare_config_data` and validate them
        using the runtime's validation context. Called during construction.

        Raises
        ------
        pydantic.ValidationError
            If the runtime or domain settings fail validation.
        """
        runtime_config = self._rc.config
        self._runtime_info = runtime_config.runtime_info
        config_data = self.prepare_config_data(runtime_config)
        config_model_cls = cast(
            "type[ConfigModelT]",
            type(self).config_model_cls,
        )
        self._config = config_model_cls.model_validate(
            config_data,
            context=self.runtime_info.validation_context,
        )

    def recreate(self) -> Self:
        """Create a handler from the attached runtime's current configuration.

        Returns
        -------
        Self
            New instance of the same handler class, with freshly validated
            settings and no inherited resource caches.

        Notes
        -----
        Does not change this handler or reread cached files. Call the runtime's
        `reload` method first if configuration files have changed.

        Examples
        --------
        >>> class Settings(BaseModel):
        ...     limit: int = 10
        >>> class Handler(
        ...     SubConfigKeyTransformer[Literal["job"]], ConfigHandler[Settings]
        ... ):
        ...     pass
        >>> rc = RuntimeContext()
        >>> handler = Handler(rc)
        >>> rc.update_override_config({"job": {"limit": 20}})
        >>> other = handler.recreate()
        >>> handler.config.limit, other.config.limit
        (10, 20)
        """
        return type(self)(self._rc)

    @contextmanager
    def temporary_config(
        self,
        *,
        defaults: DictConfigT | None = None,
        overrides: DictConfigT | None = None,
        validation_context: dict[str, Any] | None = None,
    ) -> Iterator[Self]:
        """Create a context manager for a handler with patched domain settings.

        Parameters
        ----------
        defaults, overrides : dict, optional
            Domain-shaped patches merged into the current runtime's default
            and override tiers. Defaults apply below user sources; overrides
            apply above them.
        validation_context : dict, optional
            Values to merge into the inherited validation context.

        Yields
        ------
        Self
            A separately validated handler with its own resource caches.

        See Also
        --------
        temporary_runtime_config : Apply patches using the full runtime shape.

        Examples
        --------
        >>> class Settings(BaseModel):
        ...     limit: int = 10
        >>> class Handler(
        ...     SubConfigKeyTransformer[Literal["job"]], ConfigHandler[Settings]
        ... ):
        ...     pass
        >>> handler = Handler(RuntimeContext())
        >>> with handler.temporary_config(overrides={"limit": 5}) as other:
        ...     print(other.config.limit)
        5
        >>> handler.config.limit
        10
        """
        with self.temporary_runtime_config(
            defaults=(
                self.prepare_runtime_config_data(defaults)
                if defaults is not None
                else None
            ),
            overrides=(
                self.prepare_runtime_config_data(overrides)
                if overrides is not None
                else None
            ),
            validation_context=validation_context,
        ) as handler:
            yield handler

    @contextmanager
    def temporary_runtime_config(
        self,
        *,
        defaults: DictConfigT | None = None,
        overrides: DictConfigT | None = None,
        validation_context: dict[str, Any] | None = None,
    ) -> Iterator[Self]:
        """Create a context manager for a handler with patched runtime settings.

        Parameters
        ----------
        defaults, overrides : dict, optional
            Runtime-shaped patches merged into the current default and override
            tiers before `prepare_config_data` extracts the domain settings.
        validation_context : dict, optional
            Values to merge into the inherited validation context.

        Yields
        ------
        Self
            New handler with the patched settings and validation context.

        Notes
        -----
        The original handler and runtime are unchanged. Leaving the context
        does not close resources or invalidate the yielded handler; resource
        cleanup belongs to the concrete handler or caller.

        Examples
        --------
        >>> class Settings(BaseModel):
        ...     limit: int = 10
        >>> class Handler(
        ...     SubConfigKeyTransformer[Literal["job"]], ConfigHandler[Settings]
        ... ):
        ...     pass
        >>> handler = Handler(RuntimeContext())
        >>> with handler.temporary_runtime_config(
        ...     overrides={"job": {"limit": 5}},
        ...     validation_context={"observation": 42},
        ... ) as other:
        ...     print(other.config.limit)
        ...     print(other.runtime_info.validation_context["observation"])
        5
        42
        >>> handler.config.limit
        10
        """
        runtime_context = self._rc.with_config(
            defaults=defaults,
            overrides=overrides,
            validation_context=validation_context,
        )
        yield type(self)(runtime_context)


class SubConfigKeyTransformer[KeyT: LiteralString]:
    """Mixin for handlers that extract a subkey from runtime config.

    This provides a convenient pattern for handlers that manage a specific
    section of the runtime config identified by a key.

    The subconfig_key is automatically inferred from Literal type parameters.

    Type Parameters:
        KeyT: Literal type specifying the subconfig key
            (e.g., Literal["database"])

    Example:
        >>> from typing import Literal
        >>> from pydantic import BaseModel
        >>> from tollan.config import (
        ...     ConfigHandler,
        ...     SubConfigKeyTransformer,
        ...     RuntimeContext,
        ... )
        >>>
        >>> class DatabaseConfig(BaseModel):
        ...     url: str
        >>>
        >>> class DatabaseHandler(
        ...     SubConfigKeyTransformer[Literal["database"]],
        ...     ConfigHandler[DatabaseConfig]
        ... ):
        ...     pass
        >>>
        >>> rc = RuntimeContext(
        ...     config_sources=[
        ...         {
        ...             "format": "dict",
        ...             "source": {"database": {"url": "postgresql://localhost"}},
        ...             "order": 0,
        ...         }
        ...     ]
        ... )
        >>> handler = DatabaseHandler(rc)
        >>> handler.config.url
        'postgresql://localhost'
    """

    subconfig_key: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        """Extract subconfig_key from its resolved type-variable binding."""
        super().__init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            SubConfigKeyTransformer,
            KeyT=GenericBindingRequirement("subconfig_key"),
        )
        if bindings is None:
            return
        key_annotation = bindings["KeyT"]
        key_values = get_args(key_annotation)
        if (
            get_origin(key_annotation) is not Literal
            or len(key_values) != 1
            or not isinstance(key_values[0], str)
        ):
            msg = (
                f"{cls.__name__} must bind KeyT to one string Literal, "
                f"got {key_annotation!r}"
            )
            raise TypeError(msg)
        cls.subconfig_key = key_values[0]

    @classmethod
    def prepare_config_data(cls, runtime_config: RuntimeConfig) -> dict:
        """Extract subconfig data by key.

        Parameters
        ----------
        runtime_config : RuntimeConfig
            RuntimeConfig model instance

        Returns
        -------
        dict
            Subconfig data dict
        """
        # Extract the subkey from extra fields
        # RuntimeConfig uses extra="allow", so extra fields are in __pydantic_extra__
        if (
            hasattr(runtime_config, "__pydantic_extra__")
            and runtime_config.__pydantic_extra__
        ):
            return runtime_config.__pydantic_extra__.get(cls.subconfig_key, {})
        # Fallback: try getattr (for regular fields)
        return getattr(runtime_config, cls.subconfig_key, {})

    @classmethod
    def prepare_runtime_config_data(cls, config_data: dict) -> dict:
        """Wrap config data under subconfig key.

        Parameters
        ----------
        config_data : dict
            Domain config data

        Returns
        -------
        dict
            Runtime config data with subkey
        """
        return {cls.subconfig_key: config_data}
