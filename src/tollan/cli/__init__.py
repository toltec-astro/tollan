"""Console script for tollan."""
import sys

import wrapt
from loguru import logger

from .. import _version
from ..utils.cli.multi_action_argument_parser import MultiActionArgumentParser
from ..utils.general import Deferred

main_parser = wrapt.ObjectProxy(None)
"""
A proxy to the
`tollan.utils.cli.multi_action_argument_parser.MultiActionArgumentParser`
instance, which is made available when `tolteca.cli.main` is invoked.
"""

main_parser = Deferred(MultiActionArgumentParser)


def main(args=None):
    """Console script for tollan."""
    from ..utils.cli.multi_action_argument_parser import MultiActionArgumentParser

    parser = main_parser.init(description="Tollan is a utility lib.")

    parser.add_argument("--version", "-v", action="version", version=_version.version)
    parser.add_argument(
        "-g", "--debug", help="Show debug logging messages.", action="store_true"
    )

    # load subcommands
    from . import config as _

    option, unknown_args = parser.parse_known_args(args)
    parser.parse_args(args)

    if option.debug:
        loglevel = "DEBUG"
    else:
        loglevel = "INFO"
    logger.remove()
    logger.add(sys.stderr, level=loglevel)
    logger.debug(f"{option=} {unknown_args=}")
    # invoke subcommands
    parser.bootstrap_actions(option, unknown_args=unknown_args)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
