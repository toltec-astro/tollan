import click

from ..utils.fmt import pformat_yaml
from ..utils.log import logger
from . import app

__all__ = ["cmd_check_config"]


def cmd_check_config(option, unknown_args=None):
    """Print config info."""
    logger.info(f"option: {option}, unknown_args: {unknown_args}")
    from ..config.runtime_context import RuntimeContext

    rc = RuntimeContext(option.config)
    click.echo(pformat_yaml(rc.config.model_dump()))


@app.register_action("check", callback=cmd_check_config)
def _check_config(parser):
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to the config file.",
    )
