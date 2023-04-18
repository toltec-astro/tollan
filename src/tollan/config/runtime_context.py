from __future__ import annotations

import collections.abc
import os
from functools import cached_property
from typing import Any, ClassVar

from pydantic import BaseModel, Field, create_model

from ..utils.general import rupdate
from ..utils.log import logger
from .models.config_source import ConfigSourceList
from .models.system_info import SystemInfo
from .types import ImmutableBaseModel

__all__ = ["RuntimeInfo", "RuntimeConfigBackend", "RuntimeContext"]


class RuntimeInfo(ImmutableBaseModel):
    """A default runtime info model."""

    config_sources: None | ConfigSourceList = Field(
        default=None,
        description="The config source list.",
    )
    system: SystemInfo = Field(
        default_factory=SystemInfo,
        description="The system info.",
    )


class _RuntimeConfigModelBase(ImmutableBaseModel):
    model_config = ImmutableBaseModel.model_config | {"extra": "allow"}


class _RuntimeConfigBackendBase:
    _runtime_config_model_cls: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, runtime_info_model_cls=RuntimeInfo, **kwargs):
        super().__init_subclass__(**kwargs)
        runtime_config_model_cls = create_model(
            "RuntimeConfigModel",
            __base__=_RuntimeConfigModelBase,
            runtime_info=(
                runtime_info_model_cls,
                Field(
                    default_factory=runtime_info_model_cls,
                    description="The runtime info.",
                ),
            ),
        )
        cls._runtime_config_model_cls = runtime_config_model_cls


class RuntimeConfigBackend(_RuntimeConfigBackendBase):
    """A mixin class to manage config at runtime.

    This class manages a stack of config objects `_default_config`,
    `source_config`, and `override_config`, to allow manipulating
    config dict at runtime.
    This class can be customized via subclassing by specifying
    an alternative `runtime_config_model`.
    """

    def __init__(self, config):
        self._config_sources = self._make_config_sources(config)
        # update info config recording some runtime data.
        self._info_config = {}
        self._info_config.update(
            {
                "runtime_info": {
                    "config_sources": self.sources.model_dump(),
                },
            },
        )

    _default_config: None | dict = None
    """The dict to hold default config entires."""

    _info_config: None | dict = None
    """The dict to hold info config entires."""

    _override_config: None | dict = None
    """The dict to hold override config entries."""

    _config_sources: ConfigSourceList
    """The config source list to load config from."""

    @cached_property
    def sources(self):
        """The config dict loaded from config source."""
        return self._config_sources

    @cached_property
    def source_config(self):
        """The config dict loaded from config source."""
        return self.load_source_config()

    @cached_property
    def config(self):
        """The config dict.

        This is the merged dict of `defualt_config`, `source_config`,
        and `override_config`.
        """
        return self.load()

    @classmethod
    def _make_config_sources(cls, config):
        if config is None:
            sources = [{"source": {}, "order": 0}]
        elif isinstance(config, (str, os.PathLike, collections.abc.Mapping)):
            sources = [
                {
                    "source": config,
                    "order": 0,
                },
            ]
        elif isinstance(config, collections.abc.Sequence):
            sources = list(config)
        else:
            raise TypeError(f"invalid config source type: {config}.")
        logger.debug(f"load config sources from {len(sources)} items")
        csl = ConfigSourceList.model_validate(sources)
        logger.debug(f"loaded config sources:\n{csl.model_dump_yaml()}")
        return csl

    def _make_config(self):
        config = {}
        rupdate(config, self._default_config or {})
        rupdate(config, self.source_config)
        rupdate(config, self._info_config or {})
        rupdate(config, self._override_config or {})
        return config

    def _invalidate_cache(self, *attrs):
        def _invalidate(attr):
            if attr in self.__dict__:
                del self.__dict__[attr]
                logger.debug(f"{attr} cache invalidated.")

        for attr in attrs:
            _invalidate(attr)

    def load_source_config(self):
        """Load source config."""
        self._invalidate_cache("source_config")
        return self.sources.load()

    def load(self, reload_source_config=True) -> Any:
        """Compose and return the config object.

        Parameters
        ----------
        reload_source_config : bool, optional
            If True, the :attr:`source_config` cache is invalidated and
            triggers the reload of the source config.
        """
        self._invalidate_cache("config")
        if reload_source_config:
            self._invalidate_cache("source_config")
        config = self._make_config()
        # validate the config agains config model
        return self._runtime_config_model_cls.model_validate(config)

    def dict(self, exclude_runtime_info=False) -> Any:
        """Return the config as dict.

        Parameters
        ----------
        exclude_runtime_info : bool, optional
            Control if the runtime info is excluded when dumped.
        """
        kw = {"exclude": ("runtime_info",)} if exclude_runtime_info else {}
        return self.config.model_dump(**kw)

    def yaml(self, exclude_runtime_info=False) -> Any:
        """Dump the config as YAML.

        Parameters
        ----------
        exclude_runtime_info : bool, optional
            Control if the runtime info is excluded when dumped.
        """
        kw = {"exclude": ("runtime_info",)} if exclude_runtime_info else {}
        return self.config.model_dump_yaml(**kw)

    def _set_internal_config(self, name, op, value):
        pn = f"_{name}_config"
        if not hasattr(self, pn):
            raise ValueError(f"invalid prop name {pn}")
        if op == "set":
            setattr(self, pn, value)
        elif op == "update":
            pv = getattr(self, pn)
            if pv is None:
                setattr(self, pn, value)
            else:
                rupdate(getattr(self, pn), value)
        else:
            raise ValueError(f"invalid {op=}")
        # invalidate the cache without reloading source config.
        self.__dict__["config"] = self.load(
            reload_source_config=False,
        )

    def set_default_config(self, cfg):
        """Set the default config dict.

        This will invalidate the config cache.
        """
        self._set_internal_config("default", "set", cfg)

    def set_override_config(self, cfg):
        """Set the override config dict.

        This will invalidate the config cache.
        """
        self._set_internal_config("override", "set", cfg)

    def update_default_config(self, cfg):
        """Update the default config dict.

        This will invalidate the config cache.
        """
        self._set_internal_config("default", "update", cfg)

    def update_override_config(self, cfg):
        """Update the override config dict.

        This will invalidate the config cache.
        """
        self._set_internal_config("override", "update", cfg)

    @property
    def runtime_info(self):
        """The runtime info object."""
        return self.config.runtime_info


class _RuntimeContextBase:
    _runtime_config_backend_cls: ClassVar[type[RuntimeConfigBackend]]

    def __init_subclass__(
        cls,
        runtime_config_backend_cls=RuntimeConfigBackend,
        **kwargs,
    ):
        super().__init_subclass__(**kwargs)
        cls._runtime_config_backend_cls = runtime_config_backend_cls


class RuntimeContext(_RuntimeContextBase):
    """A class to manage runtime context.

    This class acts as a proxy of an underlying runtime config backend
    object.

    This class can be customized via subclassing and one may specify an
    alternative `runtime_config_backend_cls`. This allows more specialized
    config and the runtime info generation.

    Parameters
    ----------
    *args, **kwargs :
        Argument passed to the underlying config backend class.
    """

    def __init__(self, *args, **kwargs):
        self._config_backend = self._runtime_config_backend_cls(*args, **kwargs)

    @property
    def config_backend(self):
        """The config backend."""
        return self._config_backend

    @property
    def runtime_info(self):
        """The runtime info of the context."""
        return self.config_backend.runtime_info

    @property
    def config(self):
        """The config dict."""
        return self.config_backend.config
