"""Utility functions for file operations."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import IO, Any

from astropy.utils.data import get_readable_fileobj

from .log import logger, logit

__all__ = [
    "ensure_abs_path",
    "ensure_path_parent_exists",
    "ensure_readable_fileobj",
    "get_or_create_dir",
    "resolve_symlink",
    "touch_file",
]


def ensure_abs_path(p: str | Path) -> Path:
    """Return the full expanded absolute path.

    Parameters
    ----------
    p : str | Path
        Path to expand and resolve

    Returns
    -------
    Path
        Fully expanded and resolved absolute path
    """
    return Path(p).expanduser().resolve()


def resolve_symlink(
    p: str | Path,
    n_iter_max: int | None = None,
    match_parent: Path | None = None,
) -> Path:
    """Resolve symlink chain to target path.

    Parameters
    ----------
    p : str | Path
        Path to resolve (may be symlink)
    n_iter_max : int, optional
        Maximum number of symlink resolution iterations
    match_parent : Path, optional
        Stop resolution when parent matches this path

    Returns
    -------
    Path
        Resolved target path

    Raises
    ------
    ValueError
        If maximum iteration count exceeded
    """
    p = p0 = Path(p)
    n_iter = 0
    while True:
        if not p.is_symlink():
            break
        if match_parent is not None and p.parent == match_parent:
            break
        _p = p
        p = _p.readlink()
        # relative symlink is relative to current _p.parent
        if not p.is_absolute():
            # Resolve directory links before traversing .., but leave the final
            # link for the next iteration so the stopping controls still apply.
            p = _p.parent / p
            p = p.parent.resolve() / p.name
        n_iter += 1
        if n_iter_max is not None and n_iter > n_iter_max:
            msg = f"maximum iteration exceeded when resolving symlink for {p0}"
            raise ValueError(
                msg,
            )
    return p


def ensure_readable_fileobj(
    arg: Any,
    *args,
    **kwargs,
) -> contextlib.AbstractContextManager[IO[Any]]:
    """Return a readable object.

    This differs from the `astropy.utils.data.get_readable_fileobj` in that it
    is no-op if `arg` is already readable.

    Parameters
    ----------
    arg : str | PathLike | readable object
        File path or object with read() method
    *args
        Additional arguments passed to get_readable_fileobj
    **kwargs
        Keyword arguments passed to get_readable_fileobj
    """
    if isinstance(arg, str | os.PathLike) and not Path(arg).is_dir():
        return get_readable_fileobj(arg, *args, **kwargs)
    if hasattr(arg, "read"):
        return contextlib.nullcontext(arg)
    msg = f"cannot create readable context for {arg}"
    raise ValueError(msg)


def touch_file(out_file: str | Path) -> None:
    """Touch file, the same as the shell command ``touch``.

    Parameters
    ----------
    out_file : str | Path
        Path to file to touch (create or update timestamp)
    """
    with Path(out_file).open("a"):
        os.utime(out_file, None)


def get_or_create_dir(
    dir_path: Path | str,
    on_exist: Any = None,
    on_create: Any = None,
    on_create_context: Any = None,
) -> Path:
    """Create a directory if it does not exist.

    Parameters
    ----------
    dir_path : `pathlib.Path`, str
        The path of the directory.
    on_exist : callable, optional
        If set, called if `dir_path` exists already.
    on_create : callable, optional
        If set, called if `dir_path` is created.
    on_create_context : context, optional
        The context to enter on create.

    Returns
    -------
    Path
        The created or existing directory path
    """
    dir_path = Path(dir_path)
    if dir_path.exists():
        if on_exist is not None:
            on_exist(dir_path)
        return dir_path
    with on_create_context or contextlib.nullcontext():
        dir_path.mkdir(parents=True)
    if on_create is not None:
        on_create(dir_path)
    return dir_path


def ensure_path_parent_exists(path: Path) -> Path:
    """Ensure parent path of `path` exists.

    Parameters
    ----------
    path : Path
        File path whose parent directory should be created

    Returns
    -------
    Path
        The input path unchanged
    """
    if path.is_dir():
        msg = "invalid path type."
        raise ValueError(msg)
    parent = path.parent
    get_or_create_dir(
        parent,
        on_create_context=logit(logger.info, f"create dir {parent}"),
    )
    return path
