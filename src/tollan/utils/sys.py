import contextlib
import os
import pty
import pwd
import shlex
import socket
from pathlib import Path

from .log import logger, logit

"""System related helpers."""


__all__ = [
    "ensure_path_parent_exists",
    "get_hostname",
    "get_or_create_dir",
    "get_username",
    "pty_run",
    "touch_file",
]


def get_username():
    """Return the current username."""
    # https://stackoverflow.com/a/2899055
    return pwd.getpwuid(os.getuid()).pw_name


def get_hostname():
    """Return the hostname."""
    return socket.gethostname()


def touch_file(out_file):
    """Touch file, the same as the shell command ``touch``."""
    with Path(out_file).open("a"):
        os.utime(out_file, None)


def get_or_create_dir(dirpath, on_exist=None, on_create=None, on_create_context=None):
    """Ensure `dirpath` exist.

    Parameters
    ----------
    dirpath : `pathlib.Path`, str
        The path of the directory.
    on_exist : callable, optional
        If set, called if `dirpath` exists already.
    on_create : callable, optional
        If set, called if `dirpath` is created.
    on_create_context : context, optional
        The context to enter on create.
    """
    dirpath = Path(dirpath)
    if dirpath.exists():
        if on_exist is not None:
            on_exist(dirpath)
        return dirpath
    with on_create_context or contextlib.nullcontext():
        dirpath.mkdir(parents=True)
    if on_create is not None:
        on_create(dirpath)
    return dirpath


def ensure_path_parent_exists(path: Path):
    """Ensure parent path of `path` exists."""
    if path.is_dir():
        raise ValueError("invalid path type.")
    parent = path.parent
    get_or_create_dir(
        parent,
        on_create_context=logit(logger.info, f"create dir {parent}"),
    )
    return path


def pty_run(cmd):
    """Run command in pty."""
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    cmd = list(map(str, cmd))
    cmd_str = shlex.join(cmd)
    logger.info(f"run {cmd_str} ...")
    returncode = pty.spawn(cmd)
    logger.info(f"{returncode=}: {cmd_str}")
    return returncode
