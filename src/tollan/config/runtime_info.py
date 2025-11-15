"""Runtime information for configuration context."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..utils.sys import get_hostname, get_username

__all__ = [
    "RuntimeInfo",
]


class RuntimeInfo(BaseModel):
    """Runtime environment information.

    Captures system information (user, host, platform, Python environment)
    and command-line invocation details.
    """

    username: str = Field(
        default_factory=get_username,
        description="Current username",
    )
    hostname: str = Field(
        default_factory=get_hostname,
        description="System hostname",
    )
    platform: str = Field(
        default_factory=lambda: sys.platform,
        description="Platform identifier (e.g., 'linux', 'darwin', 'win32')",
    )
    python_prefix: Path = Field(
        default_factory=lambda: Path(sys.prefix),
        description="Path to Python installation",
    )
    exec_path: Path = Field(
        default_factory=lambda: Path(sys.argv[0]) if sys.argv else Path.cwd(),
        description="Path to command-line executable",
    )
    cmd: str = Field(
        default_factory=lambda: shlex.join(sys.argv) if sys.argv else "",
        description="Invoking command line",
    )
    config_sources: Any = Field(
        default=None,
        description="Config source list for debugging and introspection",
    )
    validation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context passed to conditional config validation (enable_if)",
    )
