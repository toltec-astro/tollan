from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Literal, Union

from pydantic import Field, constr

from ..utils.general import ensure_abspath, rgetattr
from ..utils.log import logger, logit
from .types import ImmutableBaseModel

__all__ = ["PathValidationError", "validate_path", "PathItem", "DirectoryPresetMixin"]


class PathValidationError(RuntimeError):
    """Error related to path preset validation."""

    pass


def _check_path(path, type_required=None):
    # helper function to inspect path for information
    if re.search(r"[?*\[\]]", str(path)):
        # path is glob pattern
        return {
            "exists": False,
            "type_ok": type_required == "glob",
            "is_clean": False,
            "is_glob": True,
            "path": path,
        }
    # normal path file or dir
    path = ensure_abspath(path)
    result = {
        "exists": path.exists(),
        "type_ok": (not path.exists())
        or (path.is_dir() and type_required == "dir")
        or (path.is_file() and type_required == "file"),
        "is_clean": False,
        "is_glob": False,
        "path": path,
    }
    # check if path is clean
    if result["exists"] and path.is_dir():
        # empty dir is clean
        try:
            next(path.iterdir())
        except StopIteration:
            result["is_clean"] = True
        else:
            result["is_clean"] = False
    elif not result["exists"]:
        # non-exist paths are clean
        result["is_clean"] = True
    else:
        result["is_clean"] = False
    return result


def _make_backup_path(path, backup_timestamp_format, check_paths=None):
    check_paths = check_paths or []
    check_paths.append(path)
    mtime_latest = max(datetime.fromtimestamp(p.lstat().st_mtime) for p in check_paths)
    timestamp = mtime_latest.strftime(backup_timestamp_format)
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    return backup_path


def _rename_path(path, dst_path, dry_run, name):
    with logit(logger.debug, f"rename {name}: {path} -> {dst_path}"):
        if not dry_run:
            os.rename(path, dst_path)
        else:
            logger.info(f"dry run rename {name}: {path} -> {dst_path}")
    return dst_path


def _rename_as_backup(path, backup_timestamp_format, dry_run, name):
    backup_path = _make_backup_path(path, backup_timestamp_format)
    return _rename_path(path, backup_path, dry_run, name)


def _create_path(path, type_required, dry_run, name, on_create):
    # TODO create in temporary tree and move.
    with logit(logger.debug, f"create {name}: {path}"):
        if not dry_run:
            if type_required == "dir":
                if path.exists():
                    logger.debug(f"skip create {name}: {path} exists.")
                else:
                    path.mkdir(parents=True, exist_ok=False)
            elif type_required == "file":
                if path.exists():
                    logger.debug(f"overwrite {name}: {path} exists.")
                with open(path, "wb") as fo:
                    fo.write(b"")
            else:
                raise ValueError(f"unknown {name} type {type_required}")
            if on_create is not None:
                on_create(path)
        else:
            logger.info(f"dry run create {name}: {path}")
    return path


def validate_path(
    path,
    type_required,
    create=True,
    always_create=False,
    clean_create_only=True,
    backup=True,
    backup_timestamp_format="%Y%m%dT%H%M%S",
    dry_run=False,
    name=None,
    on_create=None,
):
    """
    Validate `path` as a preset path item.

    Parameters
    ----------
    path : str, `os.PathLike`
        The path to validate.

    type_required : "file", "dir", or "glob"
        The path type required.

    create : bool
        When True, missing item is created instead of raising
        validation error when `path` is invalid. This is ignored for ``glob`` type.
    always_create : bool
        When True, existing item is re-created even when no backup is made.
    clean_create_only : bool
        When True, missing item is only created when the item is clean. For
        file item, this means it does not exist, and for directory item, this
        means it either does not exist or is empty.
        This is ignored for ``glob```type.

    backup : bool
        When True, a backup of the contents are created inside `rootpath`.

    backup_timestamp_format : str
        The strftime format to use to identify the backup.

    dry_run : bool
        If True, no actual file system changed is made.

    name : str, optional
        Human readable name of this path used in error message.

    on_create : callable, optional
        Function to call when item is created.
    """
    name = name or "path"
    if "path" not in name:
        name = f"{name} path"
    c = _check_path(path=path, type_required=type_required)
    if not c["type_ok"]:
        raise PathValidationError(
            f"invalid {name}: {path} is not of type {type_required}."
        )
    # for glob pattern this is it so return
    if c["is_glob"]:
        return path
    # file or dir types
    # check against the create protocol
    if not create:
        if not c["exists"]:
            raise PathValidationError(f"missing {name}: {path} does not exists.")
        else:
            # good
            logger.debug(f"validated {name}: {path} exist and is valid")
            return path
    # check backup and do the backup, this will change the clean and exist state
    if backup and c["exists"]:
        _rename_as_backup(path, backup_timestamp_format, dry_run, name)
        c["is_clean"] = True
        c["exists"] = False

    if clean_create_only and not c["is_clean"]:
        raise PathValidationError(
            f"invalid {name}: {path} exists or is not empty. set clean_create_only=False to proceed create"
        )
    # proceed to create this item
    if c["exists"] and not always_create:
        logger.debug(
            f"validated {name}: {path} exist and creation is skipped. set always_create=True to force re-create."
        )
        return path
    # finally we create the item, this may overwrite existing item
    path = _create_path(path, type_required, dry_run, name, on_create)
    return path


RelPathStr = constr(regex=r"^(?![\/\\]+|~).*")


class PathItem(ImmutableBaseModel):
    """Item for path in file system."""

    name: str = Field(description="The name of this item.")

    path_name: RelPathStr = Field(description="The path name.")

    path_type: Literal["dir", "file", "glob"] = Field(description="The path type.")

    re_glob_ignore: str = Field(
        default=r".+.bak/.+", description="The files to ignore from glob"
    )

    on_create: Union[None, Callable] = Field(
        default=None, description="The function to call after creating this path."
    )

    def resolve_path(self, rootpath, resolve_glob=True):
        """Return the path prefixed by `rootpath`."""
        if self.path_type == "glob":
            if resolve_glob:
                # glob generator
                paths = rootpath.glob(self.path_name)
                re_glob_ignore = re.compile(self.re_glob_ignore)
                return [p for p in paths if not re.match(re_glob_ignore, str(p))]
            # glob pattern
            return str(rootpath.joinpath(self.path_name))
        # path
        return rootpath.joinpath(self.path_name)

    def validate(self, rootpath, **kwargs):
        """Validate this item under given `rootpath`.

        This invokes `validate_path` with ``kwargs`` for the resolved path.
        """
        path = self.resolve_path(rootpath, resolve_glob=False)
        return validate_path(path, self.path_type, **kwargs)


class DirectoryPresetMixin(object):
    """A mixin class to manage contents of a directory.

    The `DirectoryPresetMixin` implements the logic to setup a directory with
    pre-defined contents and the methods to manage them.

    The contents to be managed and their policies should be defined as attributes
    of a nested config class named ``Config``:

    * ``content_path_items``: a list of directory content `PathItem` definitions.

    * ``rootpath_kw``: A dict to overwrite the default rootpath PathItem. Note
    that path_name and path_type are fixed.

    Example of implementing class::

        class DirectoryPreset(DirectoryPresetMixin):
            class Config:
                content_path_items = [
                    PathItem(name='readme', path_name='README.md', path_type='file')
                ]
                rootpath_kw = {
                    "on_create": lambda path: print(f"rootpath={path}")
                }

    The path of the contents can then be accessed via instance attributes
    with name specified in the ``path_items``.
    """

    _path_items_by_attr: Dict[str, PathItem]
    _rootpath_item: PathItem
    rootpath = NotImplemented

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        rootpath_kw = rgetattr(cls, "Config.rootpath_kw", {})
        rootpath_kw.setdefault("name", "rootpath")
        rootpath_kw.update({"path_type": "dir", "path_name": ""})
        rootpath_attr_name = rootpath_kw["name"]
        path_items = [PathItem(**rootpath_kw)]
        for item in rgetattr(cls, "Config.content_path_items", []):
            path_items.append(item)
        # build a dict for random access
        path_items_by_attr = {item.name: item for item in path_items}
        cls._path_items_by_attr = path_items_by_attr
        cls._rootpath_item = path_items_by_attr[rootpath_attr_name]

    @classmethod
    def _resolve_content_path(cls, rootpath, name):
        """Return the item path prefixed by `rootpath`."""
        return cls._path_items_by_attr[name].resolve_path(rootpath=rootpath)

    @classmethod
    def get_path_attrs(cls):
        """The list of attribute names of managed paths."""
        return list(cls._path_items_by_attr.keys())

    def __getattr__(self, name, *args) -> Any:
        # make available the content attributes note rootpath is
        if name != "rootpath" and name in self._path_items_by_attr.keys():
            return self._resolve_content_path(self._rootpath, name)
        return super().__getattribute__(name, *args)

    def get_paths(self):
        """Return the dict of managed paths."""
        return {attr: getattr(self, attr) for attr in self.get_path_attrs()}

    @classmethod
    def make_inplace_backup(
        cls, rootpath, backup_timestamp_format="%Y%m%dT%H%M%S", dry_run=False
    ):
        """Helper function to create in-place backup of all managed contents."""
        if not rootpath.exists():
            raise ValueError(f"rootpath {rootpath} does not exist.")
        backup_content_paths = set()
        for item in cls._path_items_by_attr.values():
            p = item.resolve_path(rootpath, resolve_glob=True)
            if item.path_type == "glob":
                backup_content_paths.update(p)
            elif p.exists():  # type: ignore
                backup_content_paths.add(p)
            else:
                # missing item, no need to backup
                pass
        backup_name = _make_backup_path(
            rootpath, backup_timestamp_format, check_paths=list(backup_content_paths)
        ).name
        backup_path = rootpath.joinpath(backup_name)
        logger.debug(
            f"collected inplace backup\n{backup_path=}\n{backup_content_paths=}"
        )

        # go through all content paths, bulid the list of backup dst
        rename_dirs = set()
        rename_files = set()
        for p in backup_content_paths:
            if p.samefile(rootpath):
                continue
            dp = backup_path.joinpath(p.relative_to(rootpath))
            if p.is_dir():
                rename_dirs.add((p, dp))
            else:
                rename_files.add((p, dp))
        # further filter the files is any of the file is child of the dirs
        # this avoids re-creating files that are moved as part of the
        # dir.
        rename_files = [
            (s, d)
            for (s, d) in rename_files
            if not any((ds in s.parents) for (ds, _) in rename_dirs)
        ]
        rename_list = list(rename_dirs) + list(rename_files)
        # actually make the backup
        _create_path(
            path=backup_path,
            type_required="dir",
            dry_run=dry_run,
            name="backup path",
            on_create=None,
        )
        for src, dst in rename_list:
            if dst.exists():
                # TODO check if this make sense. this should be unlikely to happen...
                _rename_as_backup(
                    dst, backup_timestamp_format, dry_run=dry_run, name="backup content"
                )
            if not dst.parent.exists():
                _create_path(
                    path=dst.parent,
                    type_required="dir",
                    dry_run=dry_run,
                    name="backup content path",
                    on_create=None,
                )
            _rename_path(src, dst, dry_run=dry_run, name="backup content")

    @classmethod
    def validate(cls, rootpath, inplace_backup=False, backup=True, **kwargs):
        """
        Validate the given `rootpath` to check/create defined path items.

        This invokes `validate_path` with ``kwargs`` for the rootpath first,
        then for all content paths with pre-defined settings.

        When `inplace_backup` is set to True, the backup is done by creating
        a backup directory inside the rootpath.
        """
        # generate validate kwargs
        rootpath_vkw = kwargs
        content_vkw = kwargs.copy()
        if inplace_backup:
            # we'll handle backup manually in the loop
            rootpath_vkw["backup"] = False
            # this is needed because the rootpath is always not clean
            rootpath_vkw["clean_create_only"] = False
            content_vkw["backup"] = False
        else:
            rootpath_vkw["backup"] = backup
            content_vkw["backup"] = False

        _rootpath = None
        for item in cls._path_items_by_attr.values():
            # This assume the first item is always the rootpath
            if item is cls._rootpath_item:
                _rootpath = item.validate(rootpath, **rootpath_vkw)
                if inplace_backup:
                    cls.make_inplace_backup(
                        rootpath,
                        backup_timestamp_format="%Y%m%dT%H%M%S",
                        dry_run=kwargs.get("dry_run", False),
                    )
            else:
                ckw = kwargs.copy()
                ckw["backup"] = False
                item.validate(_rootpath, **ckw)
        return rootpath


class DirectoryPresetBase(DirectoryPresetMixin):
    """A base class for directory preset.

    Parameters
    ----------
    rootpath : str, os.PathLike
        The rootpath.
    """

    def __init__(self, rootpath):
        self._rootpath = ensure_abspath(rootpath)

    @property
    def rootpath(self):
        return self._rootpath
