"""Check command demonstrating configuration system."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..utils.fmt import pformat_yaml
from ..utils.log import logger
from ..utils.typer import MultiOption
from . import app

__all__ = ["check_config"]


@app.command(
    "check",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def check_config(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to the config file.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    env_files: Annotated[
        list[Path] | None,
        MultiOption(
            help="Path to .env file(s). Can be specified multiple times.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """
    Check and display runtime context and configuration.

    Supports arbitrary config overrides via --key=value or --key value syntax.

    [bold]Examples:[/bold]

        tollan check
        tollan check -c config.yaml
        tollan check -c config.yaml --env_files .env
        tollan check -c config.yaml --debug=true --port=8080
        tollan check --log_level DEBUG --workers 4
    """
    try:  # pragma: no cover
        from ..config.runtime_context import RuntimeContext  # noqa: PLC0415

        # Create RuntimeContext using from_cli factory method
        rc = RuntimeContext.from_cli(
            config_path=config,
            env_files=env_files,
            cli_args=ctx.args if ctx.args else None,
        )

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

    except RuntimeError as e:  # pragma: no cover
        logger.error(f"Failed to load config: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
