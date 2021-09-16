#! /usr/bin/env python

import os
import re
import inspect
import yaml
from io import StringIO, IOBase
from datetime import datetime
from pathlib import PosixPath
from yaml.dumper import SafeDumper
from schema import Schema
from dataclasses import dataclass, field
from enum import Enum, auto

import astropy.units as u

from .log import get_logger, logit
from .fmt import pformat_yaml
from .sys import touch_file
from . import rupdate, ensure_abspath


__all__ = ['DirConfYamlDumper', 'DirConfError', 'DirConfMixin']


class DirConfYamlDumper(SafeDumper):
    """Yaml dumper that handles common types in config files."""
    pass


def _quantity_representer(dumper, q):
    return dumper.represent_str(q.to_string())


def _path_representer(dumper, p):
    return dumper.represent_str(p.as_posix())


DirConfYamlDumper.add_representer(u.Quantity, _quantity_representer)
DirConfYamlDumper.add_representer(PosixPath, _path_representer)


class DirConfError(Exception):
    """Raise when errors occur in `DirConfMixin`."""
    pass


class DirConfPathType(Enum):
    """The types of item paths used by `DirConf`."""
    FILE = auto()
    DIR = auto()


@dataclass
class DirConfPath(object):
    """Item path in `DirConf`."""

    label: str
    """A descriptive name of the path"""

    path_name: str
    """The name of the path."""

    path_type: DirConfPathType
    """The type of the path, one of the types in `DirConfPathType`."""

    backup_enabled: bool = False
    """If True, the item is backed up automatically."""

    _backup_timestamp_fmt: str = field(default="%Y%m%dT%H%M%S", repr=False)
    """The suffix timestamp str to use for backup file."""

    def resolve_path(self, rootpath):
        """Return the path prefixed by `rootpath`."""
        return rootpath.joinpath(self.path_name)

    def rename_as_backup(self, rootpath, dry_run=False):
        """
        Rename the path for backup.

        Parameters
        ----------
        rootpath : `pathlib.Path`
            The rootpath to resolve the actual filepath.
        dry_run : bool
            If True, no actual rename is done.
        """
        logger = get_logger()
        path = self.resolve_path(rootpath)
        if not path.exists():
            raise DirConfError(f'cannot backup non-exists file {path}.')
        timestamp = datetime.fromtimestamp(
            path.lstat().st_mtime).strftime(
                self._backup_timestamp_fmt)
        backup_path = path.with_name(
                f"{path.name}.{timestamp}"
                )
        with logit(logger.info, f"backup {path} -> {backup_path}"):
            if not dry_run:
                os.rename(path, backup_path)
        return backup_path

    def create(self, rootpath, overwrite, dry_run):
        """
        Create this item in `rootpath`.

        Parameters
        ----------
        rootpath : `pathlib.Path`
            The rootpath to resolve the actual filepath.
        overwrite : bool
            If True, existing file is overwritten. Otherwise the
            `backup_enabled` attribute is consulted.
        dry_run : bool
            If True, no actual rename is done.
        """
        logger = get_logger()
        path = self.resolve_path(rootpath)
        item = self.label
        if path.exists():
            if overwrite:
                logger.debug(f"use existing {item} {path}")
                return path
            elif self.backup_enabled:
                logger.debug(f"backup existing {item} {path}")
                self.rename_as_backup(rootpath, dry_run=dry_run)
            else:
                # just always use existing if not set to backup
                return path
        with logit(logger.debug, f"create {item} {path}"):
            if not dry_run:
                type_ = self.path_type
                if type_ is DirConfPathType.DIR:
                    if not path.exists():
                        path.mkdir(parents=True, exist_ok=False)
                elif type_ is DirConfPathType.FILE:
                    touch_file(path)
                else:
                    # should not happen
                    raise ValueError(f"unknown {item} type")
        return path


class DirConfMixin(object):
    """A mixin class to manage contents and config files of a directory.

    The `DirConfMixin` implements the logic to setup a directory with
    pre-defined contents and manage config files within.

    The path of the contents can be accessed via instance attributes
    as defined in the `_content` dict.

    The config files are recognized by the `_config_file_pattern` class
    attribute, and :meth:`collect_config_from_files` can be used to read the
    config from the files and combine them into a single config dict object.
    By default, files with names like `10_some_thing.yaml` are recognized
    as config files.

    The mixin class expects the following class attributes from the
    instrumenting class:

    * ``_contents``

        A dictionary ``{<attr>: DirConfPath}`` that defines
        the content of the directory generated by `populate_dir`.

    The mix-in class also expects the following property:

    * ``rootpath``

        The path of the managed directory.

    """
    logger = get_logger()

    _config_file_pattern = re.compile(r'^\d+_.+\.ya?ml$')

    @staticmethod
    def _config_file_sort_key(filepath):
        """The key to sort the given config file path."""
        return int(filepath.name.split('_', 1)[0])

    @classmethod
    def _resolve_content_path(cls, rootpath, item):
        """Return the item path prefixed by `rootpath`."""
        return cls._contents[item].resolve_path(rootpath=rootpath)

    def __getattr__(self, name, *args):
        # make available the content attributes
        if name in self._contents.keys():
            return self._resolve_content_path(self.rootpath, name)
        return super().__getattribute__(name, *args)

    def _get_content_path_attrs(cls):
        return ['rootpath', ] + list(cls._contents.keys())

    def get_content_paths(self):
        """Return a dict of managed paths."""
        return {
                attr: getattr(self, attr)
                for attr in self._get_content_path_attrs()
                }

    def collect_config_files(self):
        """Return the list of config files present in the directory.

        Files with names match ``_config_file_pattern`` are returned.

        The returned files are sorted according to the sort key
        `_config_file_sort_key`.
        """
        return sorted(filter(
            lambda p: re.match(self._config_file_pattern, p.name),
            self.rootpath.iterdir()),
            key=self._config_file_sort_key)

    @classmethod
    def collect_config_from_files(cls, config_files, validate=True):
        """
        Load config from `config_files` and merge by the order.

        Parameters
        ----------
        config_files : list
            A list of configuration file paths.
        validate : bool, optional
            If True, the configuration is validated using
            :meth:`validate_config`.
        """
        if len(config_files) == 0:
            raise DirConfError("no config files specified.")
        cls.logger.debug(
                f"load config from files: {pformat_yaml(config_files)}")
        cfg = dict()
        for f in config_files:
            with open(f, 'r') as fo:
                c = yaml.safe_load(fo)
                if c is None:
                    c = dict()  # allow empty yaml file
                if not isinstance(c, dict):
                    # error if invalid config found
                    raise DirConfError(
                            f"invalid config file {f}."
                            f" No top level dict found.")
                rupdate(cfg, c)
        if validate:
            cfg = cls.validate_config(cfg)
        return cfg

    @classmethod
    def validate_config(cls, cfg):
        """Return the validated config dict from `cfg`."""
        return cls.get_config_schema().validate(cfg)

    @classmethod
    def get_config_schema(cls):
        """Return a `schema.Schema` for validating loaded config.

        This combines all :attr:`extend_config_schema` defined in all
        base classes, following the class MRO.
        """
        # merge schema
        d = dict()
        for base in reversed(inspect.getmro(cls)):
            if not hasattr(base, 'extend_config_schema'):
                continue
            if callable(base.extend_config_schema):
                s = base.extend_config_schema()
            else:
                s = base.extend_config_schema
            if s is None:
                continue
            if isinstance(s, Schema):
                s = s.schema
            rupdate(d, s)
        return Schema(d)

    yaml_dumper = DirConfYamlDumper
    """The config YAML dumper."""

    @classmethod
    def yaml_dump(cls, config, output=None):
        """Dump `config` as YAML to `output`

        Parameters
        ----------
        config : dict
            The config to write.
        output : io.StringIO, optional
            The object to write to. If None, return the YAML as string.
        """
        _output = output  # save the original output to check for None
        if output is None:
            output = StringIO()
        if not isinstance(output, IOBase):
            raise ValueError('output has to be stream object.')
        yaml.dump(config, output, Dumper=cls.yaml_dumper, sort_keys=False)
        if _output is None:
            return output.getvalue()
        return output

    @classmethod
    def yaml_load(cls, stream):
        return yaml.safe_load(stream)

    @classmethod
    def write_config_file(cls, config, filepath, overwrite=False):
        """Write `config` to `filepath`.

        Parameters
        ----------
        config : str
            The config dict to write.
        filepath : `pathlib.Path`
            The filepath to write to.
        overwrite : bool
            If True, raise `DirConfError` when `filepath` exists.
        """
        if filepath.exists() and not overwrite:
            raise DirConfError(
                    f"cannot write config to existing file {filepath}. "
                    f"Re-run with overwrite=True to proceed.")
        with open(filepath, 'w') as fo:
            cls.yaml_dump(config, output=fo)

    @classmethod
    def populate_dir(
            cls, dirpath,
            create=False,
            force=False,
            overwrite=False,
            dry_run=False,
            ):
        """
        Populate `dirpath` with the pre-defined contents.

        Parameters
        ----------
        dirpath : `pathlib.Path`, str
            The path to the work directory.

        create : bool
            When set to False, raise `DirConfError` if `path` does not
            already have all content items. Otherwise, create the missing ones.

        force : bool
            When False, raise `DirConfError` if `dirpath` is not empty

        overwrite : bool
            When False, backups are created when file exists.

        dry_run : bool
            If True, no actual file system changed is made.

        """

        dirpath = ensure_abspath(dirpath)
        # validate dirpath
        path_is_ok = False
        if dirpath.exists():
            if dirpath.is_dir():
                try:
                    next(dirpath.iterdir())
                except StopIteration:
                    # empty dir
                    path_is_ok = True
                else:
                    # nonempty dir
                    if not force:
                        raise DirConfError(
                                f"path {dirpath} is not empty. Set"
                                f" force=True to proceed anyways")
                    path_is_ok = True
            else:
                # not a dir
                raise DirConfError(
                        f"path {dirpath} exists but is not a directory."
                        )
        else:
            # non exists
            path_is_ok = True
        assert path_is_ok  # should not fail

        # create content
        for item in cls._contents.keys():
            content_path = cls._resolve_content_path(dirpath, item)
            if not create and not content_path.exists():
                raise DirConfError(
                        f"unable to initialize {cls.__name__}"
                        f" from {dirpath}:"
                        f" missing {item} {content_path}. Set"
                        f" create=True to create missing items")
            if create:
                cls._contents[item].create(
                    rootpath=dirpath, overwrite=overwrite,
                    dry_run=dry_run)
        return dirpath
