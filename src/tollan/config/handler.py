"""Configuration handler classes for domain-specific config management."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, ClassVar, Literal, LiteralString

from pydantic import BaseModel

from ..utils.typing import ensure_cls_attr_from_type_args
from .runtime_context import RuntimeContext

if TYPE_CHECKING:
    from .runtime_context import RuntimeConfig
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

    ConfigHandler provides a pattern for consuming RuntimeContext and validating
    its raw config against domain-specific models. It offers:

    - Lazy-loaded, cached domain config via `.config` property
    - Auto-reset cached properties when config updates
    - Unified interface for specialized config management
    - Subconfig extraction via SubConfigKeyTransformer pattern

    Type Parameters:
        ConfigModelT: Domain config model class (Pydantic BaseModel)
        RuntimeContextT: RuntimeContext for type hint only (default: RuntimeContext)

    Subclasses must:
        - Define ConfigModelT type parameter
        - Implement prepare_config_data() to extract config from runtime config
        - Implement prepare_runtime_config_data() to wrap config for updates

    Example:
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
        ...         return {
        ...             "database_url": "postgresql://localhost/db",
        ...             "max_connections": 20,
        ...         }
        >>>
        >>> rc = RuntimeContext(config_sources={"format": "dict", "source": {}})
        >>> handler = MyConfigHandler(rc)
        >>> handler.config.database_url
        'postgresql://localhost/db'
    """

    config_model_cls: ClassVar[type[ConfigModelT]]  # type: ignore[assignment]
    _auto_cache_reset_registry: ClassVar[dict[type, set[str]]] = {}
    _rc: RuntimeContextT

    def __init__(self, runtime_context: RuntimeContextT) -> None:
        """Initialize config handler.

        Parameters
        ----------
        runtime_context : RuntimeContext
            RuntimeContext instance
        """
        self._rc = runtime_context

    def __init_subclass__(cls, **kwargs):
        """Register subclass and infer config_model_cls from Generic parameter.

        This automatically:
        - Extracts ConfigModelT from Generic[ConfigModelT]
        - Registers the handler class with RuntimeContext
        """
        super().__init_subclass__(**kwargs)
        ensure_cls_attr_from_type_args(
            cls,
            "config_model_cls",
            max_depth=2,
            bound=BaseModel,
        )
        # Register with RuntimeContext (avoid circular import)
        from .runtime_context import RuntimeContext  # noqa: PLC0415

        RuntimeContext.register_config_handler_cls(cls)
        # Initialize auto cache registry for this class with base "config" property
        cls._auto_cache_reset_registry[cls] = {"config"}
        # Scan for properties marked with auto_cache_reset decorator
        for name, value in cls.__dict__.items():
            if isinstance(value, cached_property) and hasattr(
                value,
                "_auto_cache_reset_marker",
            ):
                cls._auto_cache_reset_registry[cls].add(name)

    @classmethod
    def auto_cache_reset(cls, prop: cached_property) -> cached_property:
        """Mark cached property for auto-reset on config reload.

        Parameters
        ----------
        prop : cached_property
            Cached property to mark

        Returns
        -------
        cached_property
            Same cached property (for chaining)

        Raises
        ------
        TypeError
            If prop is not a cached_property

        Example:
            >>> from functools import cached_property
            >>> from pydantic import BaseModel
            >>> class MyConfig(BaseModel):
            ...     value: str = "test"
            >>> class MyHandler(ConfigHandler[MyConfig]):
            ...     @classmethod
            ...     def prepare_config_data(cls, runtime_config):
            ...         return {"value": "test"}
            ...     @ConfigHandler.auto_cache_reset
            ...     @cached_property
            ...     def expensive_computation(self):
            ...         return "computed"
            >>> # Property will auto-reset when config updates
        """
        if not isinstance(prop, cached_property):
            msg = "auto_cache_reset can only be used on cached_property."
            raise TypeError(msg)
        # Mark the property for auto-reset by adding an attribute
        # The actual registration happens in __init_subclass__
        # when we know the owner class
        prop._auto_cache_reset_marker = True  # type: ignore[attr-defined]
        return prop

    @property
    def rc(self):
        """Get the underlying runtime context.

        Returns
        -------
            RuntimeContext instance
        """
        return self._rc

    @property
    def runtime_config(self):
        """Get the underlying runtime config model.

        Returns
        -------
            RuntimeConfig instance
        """
        return self.rc.config

    @property
    def runtime_info(self):
        """Get the runtime info.

        Returns
        -------
            Runtime info instance
        """
        return self.rc.runtime_info

    # note the cache is auto-reset as registered in __init_subclass__
    @cached_property
    def config(self) -> ConfigModelT:
        """Lazy-loaded, cached domain config.

        Calls load_config() on first access and caches the result.
        Cache is cleared when update_config() is called.

        Returns
        -------
            Validated config model instance
        """
        return self.load_config()

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

    def load_config(self) -> ConfigModelT:
        """Load and validate config from runtime config.

        Returns
        -------
            Validated config model instance
        """
        config_data = self.prepare_config_data(self.runtime_config)
        return self.config_model_cls.model_validate(
            config_data,
            context=self.runtime_info.validation_context,
        )

    def update_config(
        self,
        cfg: DictConfigT,
        tier: Literal["override", "default"] = "override",
    ) -> None:
        """Update config with provided config dict.

        This wraps the config under the appropriate runtime config key
        and calls update_runtime_config().

        Parameters
        ----------
        cfg : dict
            Config data to apply
        tier : Literal["override", "default"], optional
            Update tier ("override" or "default"), by default "override"
        """
        runtime_cfg = self.prepare_runtime_config_data(cfg)
        self.update_runtime_config(runtime_cfg, tier=tier)

    def update_runtime_config(
        self,
        cfg: DictConfigT,
        tier: Literal["override", "default"] = "override",
    ) -> None:
        """Update runtime config with provided dict.

        Parameters
        ----------
        cfg : DictConfigT
            Runtime config data to apply
        tier : Literal["override", "default"], optional
            Update tier, by default "override":
            - "override": Override existing values
            - "default": Use as default for unspecified values

        Raises
        ------
        ValueError
            If tier is invalid
        """
        self.rc.update_config(cfg, tier=tier)
        # Clear auto-reset cached properties
        cls = self.__class__
        if cls in cls._auto_cache_reset_registry:
            for prop in cls._auto_cache_reset_registry[cls]:
                if prop in self.__dict__:
                    del self.__dict__[prop]


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
        """Extract subconfig_key from Generic parameter."""
        super().__init_subclass__(**kwargs)
        ensure_cls_attr_from_type_args(
            cls,
            "subconfig_key",
            max_depth=3,
            type_filter=str,
        )

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
