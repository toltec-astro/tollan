"""Console script for tollan."""

import sys

from .. import _version
from ..utils.cli.argparse import MultiActionCli

__all__ = ["app"]


app = MultiActionCli(version=_version.__version__)
"""The CLI app entry point."""


@app.register_main("tollan")
def _main(parser):
    """Tollan is a utility libraray."""


# import subcommands
from . import check  # noqa: E402, F401

if __name__ == "__main__":
    sys.exit(app())  # pragma: no cover
