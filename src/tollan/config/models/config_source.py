#!/usr/bin/env python

import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Union

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
def _identify_yaml(origin, path, fileobj, *args, **kwargs):
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
    "yaml", dict, ImmutableBaseModel.Config.yaml_loads
)
config_source_io_registry.register_writer(
    "yaml", dict, ImmutableBaseModel.Config.yaml_dumps
)


# systemd env file IO
def _identify_envfile(origin, path, fileobj, *args, **kwargs):
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
        return True
    except Exception:
        pass
    return False


config_source_io_registry.register_identifier("env", dict, _identify_envfile)
config_source_io_registry.register_reader("env", dict, envfile.env_load)
config_source_io_registry.register_writer("env", dict, envfile.env_dump)


def _identify_pyobj(origin, path, fileobj, *args, **kwargs):
    # in this like both path and file should be none
    if not args:
        return False
    data = args[0]
    if not isinstance(data, (dict, list)):
        return False
    # if list, this has to be a set of cli args
    if isinstance(data, list):
        if not all(isinstance(item, str) for item in data):
            return False
    if isinstance(data, dict):
        if not all(isinstance(key, (int, str)) for key in data):
            return False
    return True


def _pyobj_load(data):
    if isinstance(data, list):
        return dict_from_cli_args(data)
    elif isinstance(data, dict):
        return dict_from_flat_dict(data)
    raise ValueError("invalid config source.")


config_source_io_registry.register_identifier("pyobj", dict, _identify_pyobj)
config_source_io_registry.register_reader("pyobj", dict, _pyobj_load)


class ConfigSource(ImmutableBaseModel):
    """The config source class.

    The config source can be anything that are registered in the `config_source_io_registry`.
    """

    io_registry: ClassVar[UnifiedIORegistry] = config_source_io_registry
    order: int = Field(
        description="The order of this config dict when merged with others."
    )
    source: Union[dict, list, AbsFilePath] = Field(description="The config source.")
    format: Union[None, Literal["env", "yaml", "pyobj"]] = Field(
        description="The config source format."
    )
    name: Union[None, str] = Field(description="Identifier of this config source.")
    enabled: bool = Field(default=True, description="Wether this config is enabled.")
    enable_if: Union[bool, str] = Field(
        default=True, description="Enable this config when this evaluates to True."
    )

    @root_validator
    def _validate_name(cls, values):
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
    def _validate_format(cls, values):
        format = values["format"]
        if format is not None:
            return values
        source = values["source"]
        if isinstance(source, os.PathLike):
            path = source
        else:
            path = None
        format = cls.io_registry.identify_format(
            "read", dict, path, None, (source,), {}
        )
        if not format:
            return values
        values["format"] = format[0]
        return values

    def is_file(self):
        return isinstance(self.source, os.PathLike)

    def is_pyobj(self):
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
                self, "__dict__", self.copy(update={"source": data}).__dict__
            )
        else:
            self.io_registry.write(data, self.source, format=self.format, **kwargs)
        return self

    def is_enabled_for(self, context: Dict[str, Any]):
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

    __root__: List[ConfigSource]

    @root_validator(pre=True)
    def _check_order_and_sort(cls, values):
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
        data = dict()
        for cs in self.__root__:
            if not cs.enabled:
                logger.debug(f"config source {cs.name} is disabled.")
                continue
            if context is None or cs.is_enabled_for(context=context):
                d = cs.load(**kwargs)
                print(f"merge {d=} to {data=}")
                rupdate(data, d)
                continue
            else:
                logger.debug(
                    f"config source {cs.name} is disabled with {cs.enable_if} "
                )
                continue
        return data

    def locate(self, config, root_key=None):
        """Return the list of sources that provides `config`.

        Parameters
        -----------
        config : str or dict
            The config key or config to locate.
        root_key : str, optional
            The root key of `config` in the global config tree.
        """
        return NotImplemented
