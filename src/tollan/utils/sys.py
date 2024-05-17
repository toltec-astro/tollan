import os
import pty
import pwd
import shlex
import socket
from pathlib import Path

from .log import logger

"""System related helpers."""


__all__ = [
    "get_username",
    "get_hostname",
    "touch_file",
    "get_or_create_dir",
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


def get_or_create_dir(dirpath, on_exist=None, on_create=None):
    """Ensure `dirpath` exist.

    Parameters
    ----------
    dirpath : `pathlib.Path`, str
        The path of the directory.
    on_exist : callable, optional
        If set, called if `dirpath` exists already.
    on_create : callable, optional
        If set, called if `dirpath` is created.
    """
    dirpath = Path(dirpath)
    if dirpath.exists():
        if on_exist is not None:
            on_exist(dirpath)
        return dirpath
    dirpath.mkdir(parents=True)
    if on_create is not None:
        on_create(dirpath)
    return dirpath


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
