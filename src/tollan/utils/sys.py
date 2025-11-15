"""System-related utility functions."""

import os
import pty
import pwd
import shlex
import socket

from .log import logger

__all__ = [
    "get_hostname",
    "get_username",
    "pty_run",
]


def get_username() -> str:
    """Return the current user's username.

    Returns
    -------
    str
        Current user's username
    """
    return pwd.getpwuid(os.getuid()).pw_name


def get_hostname() -> str:
    """Return the system hostname.

    Returns
    -------
    str
        System hostname
    """
    return socket.gethostname()


def pty_run(cmd: str | list[str]) -> int:
    """
    Run a command in a pseudo-terminal (pty).

    Parameters
    ----------
    cmd : str or list[str]
        Command to run (as a string or list of arguments).

    Returns
    -------
    int
        The exit code of the command.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    cmd = list(map(str, cmd))
    cmd_str = shlex.join(cmd)
    logger.info(f"run {cmd_str} ...")
    returncode = pty.spawn(cmd)
    logger.info(f"{returncode=}: {cmd_str}")
    return returncode
