import shlex
import sys

from pydantic import Field

from ...utils.sys import get_hostname, get_username
from ..types import AbsDirectoryPath, AbsFilePath, ImmutableBaseModel

__all__ = ["SystemInfo"]


class SystemInfo(ImmutableBaseModel):
    """The system info."""

    username: str = Field(
        default_factory=get_username,
        description="The current username.",
    )
    hostname: str = Field(
        default_factory=get_hostname,
        description="The system hostname.",
    )
    platform: str = Field(
        default_factory=lambda: sys.platform,
    )
    python_prefix: AbsDirectoryPath = Field(
        default_factory=lambda: sys.prefix,
        description="The path to the python installation.",
    )
    exec_path: AbsFilePath = Field(
        default_factory=lambda: sys.argv[0],
        description="Path to the command-line executable.",
    )
    cmd: str = Field(
        default_factory=lambda: shlex.join(sys.argv),
        description="The invoking commandline.",
    )
