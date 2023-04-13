from ..utils.log import logger
from . import main_parser

__all__ = ["cmd_config"]


def cmd_config(option, unknown_args=None):
    """Subcommand `config`."""
    logger.info(f"option: {option}, unknown_args: {unknown_args}")


if main_parser.__wrapped__ is not None:
    main_parser.add_action_parser(
        "config",
        help="Example subcommand show case the config module.",
        action=cmd_config,
    )
else:
    logger.debug(f"{__name__} loaded before main_parser is initalized.")
