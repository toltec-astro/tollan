"""Console script for tollan."""

from .. import _version
from ..utils.typer import create_cli

__all__ = ["app"]


app = create_cli(version=_version.__version__, rich_markup_mode="rich")
"""The CLI app entry point."""


# Import subcommands to register them with the app
from . import check  # noqa: E402, F401
