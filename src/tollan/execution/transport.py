"""Transports that run scheduler commands on a submission host."""

from __future__ import annotations

import shlex
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "LocalTransport",
    "SchedulerCommandError",
    "SshTransport",
    "Transport",
    "TransportError",
]

# OpenSSH reports its own failures, such as an unreachable host, with status 255.
_SSH_FAILURE = 255


class TransportError(RuntimeError):
    """The submission host could not run a command."""


class SchedulerCommandError(RuntimeError):
    """A scheduler command ran and exited with a nonzero status.

    Parameters
    ----------
    command : sequence of str
        Command that failed.
    returncode : int
        Exit status of the command.
    stderr : str
        Standard error of the command.
    """

    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"{shlex.join(self.command)} exited with status {returncode}: "
            f"{stderr.strip()}"
        )


class Transport(Protocol):
    """Runs commands on a submission host."""

    def run(self, command: Sequence[str]) -> str:
        """Run a command and return its standard output."""
        ...


def _run(
    argv: Sequence[str], command: Sequence[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 -- Commands come from scheduler code.
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        msg = f"Could not run {shlex.join(command)}: {error}"
        raise TransportError(msg) from error


class LocalTransport:
    """Run commands on this host.

    Parameters
    ----------
    timeout : float
        Seconds to wait for a command. Default is 60.
    """

    def __init__(self, *, timeout: float = 60) -> None:
        self.timeout = timeout

    def run(self, command: Sequence[str]) -> str:
        """Run a command and return its standard output.

        Parameters
        ----------
        command : sequence of str
            Executable, found on ``PATH``, and arguments.

        Returns
        -------
        str
            Standard output of the command.

        Raises
        ------
        TransportError
            The command could not start or did not finish in time.
        SchedulerCommandError
            The command exited with a nonzero status.
        """
        result = _run(command, command, timeout=self.timeout)
        if result.returncode != 0:
            raise SchedulerCommandError(command, result.returncode, result.stderr)
        return result.stdout


class SshTransport:
    """Run commands on another host through ``ssh``.

    ``ssh`` comes from ``PATH`` and uses the caller's SSH configuration, so host
    aliases, users and keys are configured there. Commands run without a
    password prompt.

    Parameters
    ----------
    host : str
        Host name or SSH configuration alias of the submission host.
    options : sequence of str
        Additional ``ssh`` arguments, such as ``["-p", "2222"]``. Default is none.
    timeout : float
        Seconds to wait for a command, including connection. Default is 60.
    connect_timeout : int
        Seconds to wait for the connection. Default is 10.
    """

    def __init__(
        self,
        host: str,
        *,
        options: Sequence[str] = (),
        timeout: float = 60,
        connect_timeout: int = 10,
    ) -> None:
        self.host = host
        self.options = list(options)
        self.timeout = timeout
        self.connect_timeout = connect_timeout

    def run(self, command: Sequence[str]) -> str:
        """Run a command on the host and return its standard output.

        Parameters
        ----------
        command : sequence of str
            Executable, found on the host's ``PATH``, and arguments. Arguments
            are quoted for the remote shell.

        Returns
        -------
        str
            Standard output of the command.

        Raises
        ------
        TransportError
            ``ssh`` could not start, connect or finish in time. A remote command
            that itself exits with status 255 is reported the same way.
        SchedulerCommandError
            The remote command exited with another nonzero status.
        """
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={self.connect_timeout}",
            *self.options,
            self.host,
            shlex.join(command),
        ]
        result = _run(argv, command, timeout=self.timeout)
        if result.returncode == _SSH_FAILURE:
            msg = f"ssh to {self.host} failed: {result.stderr.strip()}"
            raise TransportError(msg)
        if result.returncode != 0:
            raise SchedulerCommandError(command, result.returncode, result.stderr)
        return result.stdout
