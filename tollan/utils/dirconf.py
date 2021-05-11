#! /usr/bin/env python

import os
import re
import inspect
import yaml
from datetime import datetime
from pathlib import PosixPath, Path
from yaml.dumper import SafeDumper
from schema import Schema

import astropy.units as u

from .log import get_logger, logit
from .fmt import pformat_yaml
from .sys import touch_file
from . import rupdate


__all__ = ['DirConfError', 'DirConfMixin']


def _make_config_yaml_dumper():

    class yaml_dumper(SafeDumper):
        """Yaml dumper that handles some additional types."""
        pass

    yaml_dumper.add_representer(
            PosixPath, lambda s, p: s.represent_str(p.as_posix()))
    yaml_dumper.add_representer(
            u.Quantity, lambda s, q: s.represent_str(q.to_string()))
    return yaml_dumper


class DirConfError(Exception):
    """Raise when errors occur in `DirConfig`."""
    pass


class DirConfMixin(object):
    """A mix-in class for managing configuration files stored in a directory.

    The class implements the logic to setup a directory and
    populate a set of pre-defined items.

    The class manages a set of configuration files recognized by the
    `_config_file_pattern`, provides methods to load and merge the
    configuration in memory.

    The mix-in class expects the following class attributes from the
    instrumenting class:

    * ``_contents``

        A dictionary ``{<attr>: dict}`` that defines
        the content of the directory generated `populate_dir`.
        The dict for each attr should have the following keys:

        - ``path``: The path name.
        - ``type``: one of ``file`` or ``dir``
        - ``backup_enabled``: True or False.

    The mix-in class also expects the following property:

    * ``rootpath``

        The path of the mapped directory.

    """
    logger = get_logger()

    _backup_time_fmt = "%Y%m%dT%H%M%S"
    _config_file_pattern = re.compile(r'^\d+_.+\.ya?ml$')

    @staticmethod
    def _config_file_sort_key(filepath):
        """The key to sort the given configuration file path."""
        return int(filepath.name.split('_', 1)[0])

    @classmethod
    def _resolve_content_path(cls, rootpath, item):
        """Return the item path prefixed by `rootpath`."""
        return rootpath.joinpath(cls._contents[item]['path'])

    def __getattr__(self, name, *args):
        # make available the content attributes
        if name in self._contents.keys():
            return self._resolve_content_path(self.rootpath, name)
        return super().__getattribute__(name, *args)

    def _get_to_dict_attrs(cls):
        return  ['rootpath', ] + list(cls._contents.keys())

    def to_dict(self):
        """Return a dict representation of the contents."""
        return {
                attr: getattr(self, attr)
                for attr in self._get_to_dict_attrs()
                }

    def collect_config_files(self):
        """The list of configuration files present in the directory.

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
        return cls.get_config_schema().validate(cfg)

    @classmethod
    def get_config_schema(cls):
        """Return a `schema.Schema` object that validates the config.

        This combines all :attr:`extend_config_schema` defined in all
        base classes.
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

    _config_yaml_dumper = _make_config_yaml_dumper()

    @classmethod
    def write_config_to_yaml(cls, config, filepath, overwrite=False):
        if filepath.exists():
            if not overwrite:
                raise DirConfError(
                        "cannot write config to exist file. "
                        "Re-run with overwrite=True to proceed.")
        with open(filepath, 'w') as fo:
            yaml.dump(config, fo, Dumper=cls._config_yaml_dumper)

    @classmethod
    def _create_backup(cls, path, dry_run=False):
        timestamp = datetime.fromtimestamp(
            path.lstat().st_mtime).strftime(
                cls._backup_time_fmt)
        backup_path = path.with_name(
                f"{path.name}.{timestamp}"
                )
        with logit(cls.logger.info, f"backup {path} -> {backup_path}"):
            if not dry_run:
                os.rename(path, backup_path)
        return backup_path

    @classmethod
    def populate_dir(
            cls, dirpath,
            create=False, force=False, overwrite=False, dry_run=False,
            **kwargs
            ):
        """
        Populate `dirpath` with the defined items.

        Parameters
        ----------
        dirpath : `pathlib.Path`, str
            The path to the work directory.

        create : bool
            When set to False, raise `DirConfigError` if `path` does not
            already have all content items. Otherwise, create the missing ones.

        force : bool
            When False, raise `DirConfigError` if `dirpath` is not empty

        overwrite : bool
            When False, backups for existing files is created.

        dry_run : bool
            If True, no actual file system changed is made.

        kwargs : dict
            Keyword arguments passed directly into the created
            config file.
        """

        dirpath = Path(dirpath)
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
                        f"path {dirpath} exists but is not a valid directory."
                        )
        else:
            # non exists
            path_is_ok = True
        assert path_is_ok  # should not fail

        # create content
        def _get_or_create_item_path(
                item, path, overwrite=False, dry_run=False):
            backup_enabled = cls._contents[item]['backup_enabled']
            if path.exists():
                if overwrite:
                    cls.logger.debug(f"overwrite existing {item} {path}")
                elif backup_enabled:
                    cls.logger.debug(f"backup existing {item} {path}")
                    cls._create_backup(path, dry_run=dry_run)
                else:
                    # just always overwrite if not set to backup
                    pass
            else:
                with logit(cls.logger.debug, f"create {item} {path}"):
                    if not dry_run:
                        type_ = cls._contents[item]['type']
                        if type_ == 'dir':
                            path.mkdir(parents=True, exist_ok=False)
                        elif type_ == 'file':
                            touch_file(path)
                        else:
                            # should not happen
                            raise ValueError(f"unknown {item} type")

        for item in cls._contents.keys():
            content_path = cls._resolve_content_path(dirpath, item)
            if not create and not content_path.exists():
                raise DirConfError(
                        f"unable to initialize {cls.__name__}"
                        f" from {dirpath}:"
                        f" missing {item} {content_path}. Set"
                        f" create=True to create missing items")
            if create:
                _get_or_create_item_path(
                        item,
                        content_path,
                        overwrite=overwrite,
                        dry_run=dry_run)
        return dirpath
