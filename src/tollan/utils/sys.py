import os
import pwd
import socket
from pathlib import Path

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
    """Same as the shell command `hostname`"""
    return socket.gethostname()


def touch_file(out_file):
    """Same as the shell command `touch`."""

    with open(out_file, "a"):
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
    os.makedirs(dirpath)
    if on_create is not None:
        on_create(dirpath)
    return dirpath
