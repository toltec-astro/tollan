from __future__ import annotations

import collections.abc
import functools
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, Literal, get_args

# import numpy as np
import pandas as pd
from astropy.io.registry import UnifiedIORegistry
from pydantic import Field, ValidationInfo, field_validator, model_validator

from ...utils import envfile
from ...utils.cli import dict_from_cli_args
from ...utils.general import dict_from_flat_dict, rupdate
from ...utils.log import logger
from ..types import AbsFilePath, ImmutableBaseModel

__all__ = ["config_source_io_registry", "ConfigSource", "ConfigSourceList"]

config_source_io_registry = UnifiedIORegistry()
"""An unified IO registry for load and dump config files."""

_FileSourceFormat = Literal["env", "yaml"]
_PyObjSourceFormat = Literal["dict", "config_source_list", "cli_args"]


class ConfigSource(ImmutableBaseModel):
    """The config source class.

    The config source can be anything that are registered in the
    `config_source_io_registry`.
    """

    io_registry: ClassVar[UnifiedIORegistry] = config_source_io_registry
    order: int = Field(
        description="The order of this config dict when merged with others.",
    )
    source: AbsFilePath | dict | list | ConfigSourceList = Field(
        # union_mode='left_to_right',
        description="The config source.",
    )
    format: _FileSourceFormat | _PyObjSourceFormat = Field(
        description="The config source format.",
    )
    name: None | str = Field(
        default=None,
        description="The config source name.",
    )
    enabled: bool = Field(default=True, description="Wether this config is enabled.")
    enable_if: None | str = Field(
        default=None,
        description="If set, this config is conditional depends on the context.",
    )

    @model_validator(mode="before")
    @classmethod
    def _validate_name_format(cls, values):
        source = values.get("source", None)
        if source is None:
            # let pydantic core to raise because no source is given.
            return values
        source_is_path_like = isinstance(source, str | os.PathLike)
        format = values.get("format", None)
        if format is None:
            valid_formats = cls.io_registry.identify_format(
                "read",
                dict,
                source if source_is_path_like else None,
                None,
                (source,),
                {},
            )
            if valid_formats:
                values["format"] = valid_formats[0]
        format = values.get("format", None)
        name = values.get("name", None)
        if name is None:
            if source_is_path_like:
                name = str(source)
            elif isinstance(source, ConfigSourceList):
                name = source.name
            else:
                pass
            values["name"] = name
        return values

    @field_validator("source", mode="before")
    @classmethod
    def _validate_source(cls, value):
        # make sure the string is interpreted as path
        if isinstance(value, str):
            return Path(value)
        return value

    def is_file(self):
        """Check if the config source is file."""
        return isinstance(self.source, os.PathLike)

    def is_pyobj(self):
        """Check if the config source is in-memory object."""
        return not self.is_file()

    def load(self, **kwargs):
        """Load config from source."""
        return self.io_registry.read(dict, self.source, format=self.format, **kwargs)

    def dump(self, data, **kwargs):
        """Dump config to source."""
        if self.is_file():
            self.io_registry.write(data, self.source, format=self.format, **kwargs)
        else:
            # change the source directly. Note this relies on the internals
            # of pydantic
            object.__setattr__(
                self,
                "__dict__",
                self.model_copy(update={"source": data}).__dict__,
            )
        return self

    def is_enabled_for(self, context: None | dict[str, Any]):
        """Check if the config source is enabled for given context."""
        if not self.enabled:
            return False
        if self.enable_if is None:
            return self.enabled
        # enable_if is something. In this case we require context to be also present
        if context is None:
            logger.debug(
                "enable_if is set but no context is provided, config is disabled.",
            )
            return False
        # invoke enable_if
        if isinstance(context, dict):
            # wrap this in a pandas dataframe
            tbl_context = pd.DataFrame.from_records([context])
        elif isinstance(context, pd.DataFrame):
            tbl_context = context
        else:
            raise TypeError("invalid context type.")
        result = tbl_context.query(
            self.enable_if,
            local_dict={},
            global_dict={},
        )
        return len(result) > 0
        # # the pd eval returns np bool
        # if isinstance(result, bool | np.bool_):
        #     return result
        # raise ValueError(f"ambiguous enabled_if result: {result}")


class ConfigSourceList(ImmutableBaseModel):
    """A base class to manage multiple config sources."""

    data: list[ConfigSource] = Field(
        description="The config sources.",
    )

    name: None | str = Field(
        default=None,
        description="The name.",
    )

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, item: int):
        return self.data[item]

    @model_validator(mode="before")
    @classmethod
    def _validate_arg(cls, arg):
        if isinstance(arg, list):
            # wrap this as the dict data
            return {
                "data": arg,
            }
        if isinstance(arg, dict):
            return arg
        raise ValueError("invalid config source list data.")

    @field_validator("data", mode="before")
    @classmethod
    def _check_data_order_and_sort(cls, data, info: ValidationInfo):
        if not isinstance(data, collections.abc.Sequence):
            # note this has to raise type error to signal failed validation
            # which is required when this class is used in a union type.
            raise ValueError("invalid sources type.")  # noqa: TRY004
        implicit_order = (info.context or {}).get("config_source_implicit_order", False)
        if implicit_order:
            data = deepcopy(data)
            for i, source in enumerate(data):
                source.setdefault("order", i)
        orders = [source["order"] for source in data]
        if len(set(orders)) != len(orders):
            raise ValueError(f"order of config sources is ambiguous:\n{data}")
        # sort by orders
        return sorted(data, key=lambda s: s["order"])

    def load(self, context=None, **kwargs):
        """Load config from all sources.

        Parameters
        ----------
        context : dict, optional
            The context object to pass to `ConfigSource.is_enabled_for`.
        """
        data = {}
        for i, cs in enumerate(self):
            if not cs.enabled:
                logger.debug(f"config source {cs.name} is disabled.")
                continue
            if cs.is_enabled_for(context=context):
                d = cs.load(context=context, **kwargs)
                # logger.debug(f"merge {d} to {data}")
                rupdate(data, d)
                msg = "enabled"
            else:
                msg = "disabled"
            enable_if = cs.enable_if
            if enable_if is not None:
                name = cs.name or "<unnamed>"
                order = cs.order
                logger.debug(
                    f"config source of {name=} {order=} at {i=} "
                    f"is {msg} by {enable_if=} {context=}",
                )
            continue
        return data

    def locate(self, _config, _root_key=None):
        """Return the list of sources that provides `config`.

        Parameters
        ----------
        config : str or dict
            The config key or config to locate.
        root_key : str, optional
            The root key of `config` in the global config tree.
        """
        return NotImplemented


# Config source pyobj IO


def _get_pyobj_format(data) -> None | _PyObjSourceFormat:  # noqa: PLR0911
    if not isinstance(data, dict | list | ConfigSourceList):
        return None
    # if dict, this has to have int or str keys
    if isinstance(data, dict) and all(isinstance(key, int | str) for key in data):
        return "dict"
    # if list, this can be cli_args or config source list
    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            return "config_source_list"
        # assume to be cli args
        if all(isinstance(item, str) for item in data):
            return "cli_args"
        return None
    if isinstance(data, ConfigSourceList):
        return "config_source_list"
    return None


def _identify_pyobj(
    origin,  # noqa: ARG001
    path,  # noqa: ARG001
    fileobj,  # noqa: ARG001
    *args,
    format_expected: None | _PyObjSourceFormat = None,
    **kwargs,  # noqa: ARG001
):
    if not args:
        return False
    data = args[0]
    return _get_pyobj_format(data) == format_expected


def _pyobj_load(data, context=None, format: None | _PyObjSourceFormat = None):
    if format == "dict":
        return dict_from_flat_dict(data)
    if format == "config_source_list":
        if not isinstance(data, ConfigSourceList):
            data = ConfigSourceList.model_validate(
                data,
                context={"config_source_implicit_order": True},
            )
        logger.debug(f"load config from source list {data}")
        return data.load(context=context)
    if format == "cli_args":
        return dict_from_cli_args(data)
    raise ValueError("invalid config source.")


for fmt in get_args(_PyObjSourceFormat):
    config_source_io_registry.register_identifier(
        fmt,
        dict,
        functools.partial(_identify_pyobj, format_expected=fmt),
    )
    config_source_io_registry.register_reader(
        fmt,
        dict,
        functools.partial(_pyobj_load, format=fmt),
    )


# config source file IO
# these are know format that we check to by pass content check in identify
_config_file_path_exts: dict[_FileSourceFormat, set[str]] = {
    "yaml": {
        ".yaml",
        ".yml",
    },
    "env": {
        ".env",
    },
}


# this is used to skip context check for some obvious cases.
def _config_file_skip_content_check(path: Path):
    return path.suffix in {
        ".nc",
        ".ecsv",
        ".csv",
        ".env",
        ".yaml",
        ".yml",
    }


def _get_config_file_path(path, fileobj):
    if path is None:
        if hasattr(fileobj, "name"):
            path = fileobj.name
        else:
            return None
    return Path(path)


def _identify_yaml(origin, path, fileobj, *args, **_kwargs):  # noqa: ARG001
    path = _get_config_file_path(path, fileobj)
    if path is None:
        return False
    if path.suffix in _config_file_path_exts["yaml"]:
        return True
    # here we skip content check for all cases
    return False


def _yaml_load(path, context=None):
    data = ImmutableBaseModel.yaml_load(path)
    fmt = _get_pyobj_format(data)
    if fmt in ["dict", "config_source_list"]:
        # read with pyobj reader
        logger.debug(f"load {fmt} data from yaml file {path}")
        return _pyobj_load(data, context=context, format=fmt)
    raise ValueError(f"invalid config object type in yaml file {path}")


config_source_io_registry.register_identifier("yaml", dict, _identify_yaml)
config_source_io_registry.register_reader(
    "yaml",
    dict,
    _yaml_load,
)
# TODO: revisit this. This does not work for config sources in yaml file.
config_source_io_registry.register_writer(
    "yaml",
    dict,
    ImmutableBaseModel.yaml_dump,
)


# systemd env file IO
def _identify_envfile(origin, path, fileobj, *args, **_kwargs):  # noqa: ARG001
    path = _get_config_file_path(path, fileobj)
    if path is None:
        return False
    if path.suffix in _config_file_path_exts["env"]:
        return True
    if _config_file_skip_content_check(path):
        return False
    # do content check
    # try:
    #     envfile.env_load(path)
    # except Exception:
    #     logger.debug(f"unable to open {path} as envfile.")
    # else:
    #     return True
    return False


config_source_io_registry.register_identifier("env", dict, _identify_envfile)
config_source_io_registry.register_reader("env", dict, envfile.env_load)
config_source_io_registry.register_writer("env", dict, envfile.env_dump)
