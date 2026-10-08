"""Check command demonstrating configuration system."""

from __future__ import annotations

import typer

from ..config import RuntimeContext
from ..utils.fmt import pformat_yaml
from ..utils.log import logger
from . import app

__all__ = ["check_config"]


@app.command(
    "check",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@RuntimeContext.add_cli_options()
def check_config(
    ctx: typer.Context,
) -> None:
    """
    Check and display runtime context and configuration.

    Supports arbitrary config overrides via --key=value or --key value syntax.

    [bold]Examples:[/bold]

        tollan check
        tollan check -c config.yaml
        tollan check -c config.d override.yaml --env_paths env.d local.env
        tollan check -c config.yaml --debug=true --port=8080
        tollan --log_level DEBUG check --workers 4
    """
    try:
        rc = RuntimeContext.from_cli_ctx(ctx, cli_args=ctx.args or None)

        # Display runtime info
        typer.echo("Runtime Context:")
        typer.echo(pformat_yaml(rc.runtime_info.model_dump()))

        # Display CLI args if any
        if ctx.args:
            typer.echo("\nCLI Arguments:")
            typer.echo(pformat_yaml({"args": ctx.args}))

        # Display full config
        typer.echo("\nConfiguration:")
        typer.echo(pformat_yaml(rc.config.model_dump(exclude={"runtime_info"})))

    except RuntimeError as e:
        logger.error(f"Failed to load config: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
