from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Literal

import pandas as pd
from astropy.io.registry import UnifiedIORegistry
from pydantic import Field, root_validator

from ...utils import envfile
from ...utils.cli import dict_from_cli_args
from ...utils.general import dict_from_flat_dict, rupdate
from ...utils.log import logger
from ..types import AbsFilePath, ImmutableBaseModel

__all__ = ["config_source_io_registry", "ConfigSource", "ConfigSourceList"]

config_source_io_registry = UnifiedIORegistry()
"""An unified IO registry for load and dump config files."""


# YAML IO
def _identify_yaml(origin, path, fileobj, *args, **kwargs):  # noqa: ARG001
    if path is None:
        if hasattr(fileobj, "name"):
            path = fileobj.name
        else:
            return False
    path = Path(path)
    if path.suffix in [".yaml", "yml"]:
        return True
    return False


config_source_io_registry.register_identifier("yaml", dict, _identify_yaml)
config_source_io_registry.register_reader(
    "yaml",
    dict,
    ImmutableBaseModel.Config.yaml_loads,
)
config_source_io_registry.register_writer(
    "yaml",
    dict,
    ImmutableBaseModel.Config.yaml_dumps,
)


# systemd env file IO
def _identify_envfile(origin, path, fileobj, *args, **kwargs):  # noqa: ARG001
    if path is None:
        if hasattr(fileobj, "name"):
            path = fileobj.name
        else:
            return False
    path = Path(path)
    if path.suffix in [".env"]:
        return True
    try:
        envfile.env_load(path)
    except Exception:  # noqa: BLE001
        logger.debug(f"unable to open {path} as envfile.")
    else:
        return True
    return False


config_source_io_registry.register_identifier("env", dict, _identify_envfile)
config_source_io_registry.register_reader("env", dict, envfile.env_load)
config_source_io_registry.register_writer("env", dict, envfile.env_dump)


def _identify_pyobj(origin, path, fileobj, *args, **kwargs):  # noqa: ARG001
    # in this like both path and file should be none
    if not args:
        return False
    data = args[0]
    if not isinstance(data, (dict, list)):
        return False
    # if list, this has to be a set of cli args
    if isinstance(data, list) and not all(isinstance(item, str) for item in data):
        return False
    if isinstance(data, dict) and not all(isinstance(key, (int, str)) for key in data):
        return False
    return True


def _pyobj_load(data):
    if isinstance(data, list):
        return dict_from_cli_args(data)
    if isinstance(data, dict):
        return dict_from_flat_dict(data)
    raise ValueError("invalid config source.")


config_source_io_registry.register_identifier("pyobj", dict, _identify_pyobj)
config_source_io_registry.register_reader("pyobj", dict, _pyobj_load)


class ConfigSource(ImmutableBaseModel):
    """The config source class.

    The config source can be anything that are registered in the
    `config_source_io_registry`.
    """

    io_registry: ClassVar[UnifiedIORegistry] = config_source_io_registry
    order: int = Field(
        description="The order of this config dict when merged with others.",
    )
    source: dict | list | AbsFilePath = Field(  # type: ignore
        description="The config source.",
    )
    format: None | Literal["env", "yaml", "pyobj"] = Field(
        description="The config source format.",
    )
    name: None | str = Field(description="Identifier of this config source.")
    enabled: bool = Field(default=True, description="Wether this config is enabled.")
    enable_if: bool | str = Field(
        default=True,
        description="Enable this config when this evaluates to True.",
    )

    @root_validator
    def _validate_name(cls, values):  # noqa: N805
        name = values["name"]
        if name is not None:
            return values
        source = values["source"]
        if isinstance(source, os.PathLike):
            values["name"] = str(source)
        else:
            values["name"] = "pyobj"
        return values

    @root_validator
    def _validate_format(cls, values):  # noqa: N805
        format = values["format"]
        if format is not None:
            return values
        source = values["source"]
        path = source if isinstance(source, os.PathLike) else None
        format = cls.io_registry.identify_format(
            "read",
            dict,
            path,
            None,
            (source,),
            {},
        )
        if not format:
            return values
        values["format"] = format[0]
        return values

    def is_file(self):
        """Check if the config source is file."""
        return isinstance(self.source, os.PathLike)

    def is_pyobj(self):
        """Check if the config source is in-memory object."""
        return isinstance(self.source, (dict, list))

    def load(self, **kwargs):
        """Load config from source."""
        return self.io_registry.read(dict, self.source, format=self.format, **kwargs)

    def dump(self, data, **kwargs):
        """Dump config to source."""
        if not self.is_file():
            # change the source directly. Note this relies on the internals
            # of pydantic
            object.__setattr__(
                self,
                "__dict__",
                self.copy(update={"source": data}).__dict__,
            )
        else:
            self.io_registry.write(data, self.source, format=self.format, **kwargs)
        return self

    def is_enabled_for(self, context: dict[str, Any]):
        """Check if the config source is enabled for given context."""
        if not self.enabled:
            return False
        if isinstance(self.enable_if, bool):
            return self.enabled
        # evaluate
        result = pd.eval(self.enable_if, resolvers=[context])
        if isinstance(result, bool):
            return result
        raise ValueError(f"ambiguous enabled_if result: {result}")


class ConfigSourceList(ImmutableBaseModel):
    """A base class to manage multiple config sources."""

    __root__: list[ConfigSource]

    @root_validator(pre=True)
    def _check_order_and_sort(cls, values):  # noqa: N805
        sources = values.get("__root__")
        orders = [source.get("order") for source in sources]
        if len(set(orders)) != len(orders):
            raise ValueError(f"order of config sources is ambiguous:\n{sources}")
        # sort by orders
        sources_sorted = sorted(sources, key=lambda s: s.get("order"))
        values["__root__"] = sources_sorted
        return values

    def __iter__(self):
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]

    def load(self, context=None, **kwargs):
        """Load config from all sources.

        Parameters
        ----------
        context : dict, optional
            The context object to pass to `ConfigSource.is_enabled_for`.
        """
        data = {}
        for cs in self.__root__:
            if not cs.enabled:
                logger.debug(f"config source {cs.name} is disabled.")
                continue
            if context is None or cs.is_enabled_for(context=context):
                d = cs.load(**kwargs)
                logger.debug(f"merge {d=} to {data=}")
                rupdate(data, d)
                continue
            logger.debug(f"config source {cs.name} is disabled with {cs.enable_if} ")
            continue
        return data

    def locate(self, config, root_key=None):  # noqa: ARG002
        """Return the list of sources that provides `config`.

        Parameters
        ----------
        config : str or dict
            The config key or config to locate.
        root_key : str, optional
            The root key of `config` in the global config tree.
        """
        return NotImplemented
