from ..utils.log import logger, logit
from . import main_parser

__all__ = ["cmd_config"]


def cmd_config(option, unknown_args=None):
    logger.info(f"option: {option}")


if main_parser.__wrapped__ is not None:
    main_parser.add_action_parser(
        "config",
        help="Example subcommand show case the config module.",
        action=cmd_config,
    )
else:
    raise RuntimeError("main_parser is not initalized.")
