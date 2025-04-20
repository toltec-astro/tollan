import functools
from collections.abc import Callable
from typing import override

import click
import typer
import typer.core
import typer.utils

from ..log import logger, reset_logger


def create_cli(version=None) -> tuple[typer.Typer, Callable]:
    """Return a new CLI app."""
    app = typer.Typer(
        context_settings={"help_option_names": ["-h", "--help"]},
    )

    app.callback = functools.partial(app.callback, cls=_Group)

    if version is not None:

        @app.command("version", add_help_option=False)
        def _version():
            """Print version."""
            typer.echo(f"{version}")

    return app


def _help_all_callback(
    ctx: click.Context,
    param: click.Parameter,  # noqa: ARG001
    value: bool,
):
    """Show full help and exit."""
    if ctx.resilient_parsing:
        return
    if value:
        typer.echo(ctx.get_help())
        typer.echo("\nSubcommand Details:\n" + "=" * 20)
        for name, command in ctx.command.commands.items():
            typer.echo(f"\nCommand: {name}")
            typer.echo(command.get_help(ctx))
        raise typer.Exit(code=0)


def _reset_logger_callback(
    ctx: click.Context,
    param: click.Parameter,  # noqa: ARG001
    value: str,
):
    """Set the log level."""
    if ctx.resilient_parsing:
        return
    reset_logger(level=value, verbose=False)
    logger.debug(f"reset looger: level={value}")


class _Group(typer.core.TyperGroup):

    @override
    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        params = super().get_params(ctx)

        help_all_opt = typer.core.TyperOption(
            param_decls=["--help_all"],
            type=bool,
            is_flag=True,
            show_default=False,
            callback=_help_all_callback,
            help=_help_all_callback.__doc__,
            is_eager=True,
        )
        log_level_opt = typer.core.TyperOption(
            param_decls=["--log_level", "-l"],
            type=str,
            default="INFO",
            show_default=True,
            callback=_reset_logger_callback,
            help="Set the log level.",
            is_eager=True,
        )
        params.extend([help_all_opt, log_level_opt])
        return params

    @override
    def invoke(self, ctx: click.Context):
        for pname in ["help_all", "log_level"]:
            if pname in ctx.params:
                del ctx.params[pname]
        return super().invoke(ctx)
