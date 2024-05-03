from __future__ import annotations

import collections.abc
import os
import re
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import Field, create_model

from ..utils.general import dict_from_regex_match, rupdate
from ..utils.log import logger
from ..utils.typing import get_typing_args
from .models.config_source import ConfigSourceList
from .models.system_info import SystemInfo
from .types import ImmutableBaseModel, TimeField

__all__ = ["RuntimeInfo", "ConfigBackend", "RuntimeContext"]


RuntimeInfoModelT = TypeVar("RuntimeInfoModelT", bound=ImmutableBaseModel)


class _ConfigModelBase(ImmutableBaseModel, Generic[RuntimeInfoModelT]):
    model_config = ImmutableBaseModel.model_config | {"extra": "allow"}
    runtime_info: RuntimeInfoModelT


class ConfigBackendBase(Generic[RuntimeInfoModelT]):
    """A base class to manage a set of config sources.

    This class manages a stack of config objects ``default_config``,
    ``source_config``, and ``override_config``, to allow manipulating
    config dict at runtime.
    This class shall be customized via subclassing by specifying
    the ``RuntimeInfoModelT``.
    """

    runtime_info_model_cls: ClassVar[type[RuntimeInfoModelT]]
    config_model_cls: ClassVar[type[_ConfigModelBase[RuntimeInfoModelT]]]

    def __init_subclass__(cls, **kwargs):
        runtime_info_model_cls = get_typing_args(
            cls,
            max_depth=2,
            bound=ImmutableBaseModel,
            unique=True,
        )
        # this is needed to replace the model cls with default_factory.
        config_model_cls = create_model(
            "ConfigModel",
            __base__=_ConfigModelBase[runtime_info_model_cls],
            runtime_info=(
                runtime_info_model_cls,
                Field(
                    default_factory=runtime_info_model_cls,
                    description="The runtime info.",
                ),
            ),
        )
        cls.runtime_info_model_cls = runtime_info_model_cls
        cls.config_model_cls = config_model_cls
        super().__init_subclass__(**kwargs)

    def __init__(self, config=None):
        self._config_sources = self._resolve_config_sources(config)
        self._update_info_config()

    @classmethod
    def _resolve_config_sources(cls, arg):
        if isinstance(arg, ConfigSourceList):
            return arg
        if arg is None or isinstance(arg, collections.abc.Mapping):
            sources = [{"source": arg or {}, "order": 0}]
        elif isinstance(arg, str | os.PathLike):
            path = Path(arg)
            if path.is_dir():
                sources = cls._resolve_config_sources_from_dir(path)
            else:
                sources = [
                    {
                        "source": path,
                        "order": 0,
                    },
                ]
        elif isinstance(arg, collections.abc.Sequence):
            sources = list(arg)
        else:
            raise TypeError(f"invalid config source arg type: {arg}.")
        logger.debug(f"load config sources from {len(sources)} items")
        csl = ConfigSourceList.model_validate(sources)
        logger.debug(f"loaded config sources:\n{csl.model_dump_yaml()}")
        return csl

    _re_dir_config_source: ClassVar = re.compile(r"^(?P<order>\d+)(_.*)?\.ya?ml$")

    def _get_dir_config_source_order(path, path_info):  # noqa: N805
        return int(path_info["order"])

    @classmethod
    def _resolve_config_sources_from_dir(cls, path: Path):
        sources = []
        for p in path.iterdir():
            m = dict_from_regex_match(
                cls._re_dir_config_source,
                p.name,
            )
            if m is None:
                continue
            sources.append(
                {
                    "source": p,
                    "order": cls._get_dir_config_source_order(p, m),
                },
            )
        return sources

    _default_config: None | dict = None
    """The dict to hold default config entires."""

    _info_config: None | dict = None
    """The dict to hold info config entires."""

    _override_config: None | dict = None
    """The dict to hold override config entries."""

    _config_sources: ConfigSourceList
    """The config source list to load config from."""

    @cached_property
    def sources(self) -> ConfigSourceList:
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

    def _update_info_config(self):
        """Populate the info config.

        Subclass may override this function to customize the runtime info
        generated by modifying `_info_config`.
        """
        if self._info_config is None:
            self._info_config = {}
        rupdate(
            self._info_config,
            {
                "runtime_info": {
                    "validation_context": {},
                    "config_sources": self.sources.model_dump(),
                },
            },
        )

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

    def load(self, reload_source_config=True):
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
        return self.config_model_cls.model_validate(
            config,
            # TODO: may need to check if the key exists?
            context=config["runtime_info"]["validation_context"],
        )

    def dict(self, exclude_runtime_info=False):
        """Return the config as dict.

        Parameters
        ----------
        exclude_runtime_info : bool, optional
            Control if the runtime info is excluded when dumped.
        """
        kw = {"exclude": ("runtime_info",)} if exclude_runtime_info else {}
        return self.config.model_dump(**kw)

    def yaml(self, exclude_runtime_info=False):
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


ConfigBackendT = TypeVar("ConfigBackendT", bound=ConfigBackendBase)


class RuntimeContextBase(Generic[ConfigBackendT, RuntimeInfoModelT]):
    """A base class to manage runtime context.

    This class acts as a proxy of an underlying runtime config backend
    object.

    This class shall be customized via subclassing
    and specifying the `config_backend_cls` keyword argument.

    Parameters
    ----------
    *args, **kwargs :
        Specify the underlying runtime config backend.
        If only one arg passed and it is of type `ConfigBackend`,
        it is used as as-is, otherwise these arguments are passed
        to the `_config_backend_cls` constructor.
    """

    config_backend_cls: ClassVar[type[ConfigBackendT]]
    _config_backend: ConfigBackendT

    def __init_subclass__(
        cls,
        **kwargs,
    ):
        cls.config_backend_cls = get_typing_args(
            cls,
            max_depth=2,
            bound=ConfigBackendBase,
            unique=True,
        )
        super().__init_subclass__(**kwargs)

    def __init__(self, *args, **kwargs):
        self._config_backend = self.get_or_create_config_backend(*args, **kwargs)

    @classmethod
    def get_or_create_config_backend(cls, *args, **kwargs):
        if (
            len(args) == 1
            and len(kwargs) == 0
            and isinstance(args[0], cls.config_backend_cls)
        ):
            return args[0]
        return cls.config_backend_cls(*args, **kwargs)

    @property
    def config_backend(self):
        """The config backend."""
        return self._config_backend

    @property
    def runtime_info(self) -> RuntimeInfoModelT:
        """The runtime info of the context."""
        return self.config_backend.runtime_info

    @property
    def config(self):
        """The config dict."""
        return self.config_backend.config


##  A set of default implementations:
class RuntimeInfo(ImmutableBaseModel):
    """A default runtime info model."""

    created_at: TimeField = Field(
        default_factory=TimeField.now,
        description="The creation time",
    )
    config_sources: None | ConfigSourceList = Field(
        default=None,
        description="The config source list.",
    )
    system: SystemInfo = Field(
        default_factory=SystemInfo,
        description="The system info.",
    )
    validation_context: dict = Field(
        default_factory=dict,
        description="Context passed to model validation function.",
    )


class ConfigBackend(ConfigBackendBase[RuntimeInfo]):
    """A default config backend."""


class RuntimeContext(RuntimeContextBase[ConfigBackend, RuntimeInfo]):
    """A default runtime context."""
