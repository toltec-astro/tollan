"""Typer CLI utility functions.

This module extends Typer's CLI functionality with custom options and utilities.
The main feature is MultiOption, which enables variable-length option arguments
in Tollan Typer commands, with automatic type conversion via Typer's built-in
system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from rich.console import Console
from rich.rule import Rule

if TYPE_CHECKING:
    from collections.abc import Callable

import click
import typer
import typer.core
from typer.models import OptionInfo
from typer.utils import get_params_from_function

from .log import logger, reset_logger

__all__ = [
    "MultiOption",
    "MultiOptionInfo",
    "TollanTyper",
    "create_cli",
]


def create_cli(version: str = "dev", **kwargs) -> typer.Typer:
    """Return a new CLI app with reasonable defaults.

    Parameters
    ----------
    version : str
        Version string to display with the version command.
    **kwargs
        Additional keyword arguments to pass to typer.Typer().
    """
    # Set reasonable defaults, allowing caller to override
    typer_kwargs: dict[str, Any] = {
        "context_settings": {"help_option_names": ["-h", "--help"]},
        "cls": _Group,
    }
    typer_kwargs.update(kwargs)

    app = TollanTyper(**typer_kwargs)

    @app.callback(invoke_without_command=True)
    def main(ctx: typer.Context) -> None:
        # If no command is provided, show help
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit

    @app.command("version", add_help_option=False)
    def _version():
        """Print version."""
        typer.echo(f"{version}")

    return app


def _help_all_callback(
    ctx: click.Context,
    param: click.Parameter,
    value: bool,  # noqa: FBT001
) -> None:
    """Show full help and exit."""
    if ctx.resilient_parsing:
        return
    if value:
        console = Console()
        # Show main help
        console.print(ctx.get_help())
        # Show subcommand details with Rich dividers
        if hasattr(ctx.command, "commands"):
            for name, command in cast("click.Group", ctx.command).commands.items():
                console.print()
                console.print(
                    Rule(
                        f"[bold cyan]Command: {name}[/bold cyan]",
                        style="blue",
                        align="left",
                    ),
                )
                console.print()
                command.get_help(ctx)
        raise typer.Exit(code=0)


def _reset_logger_callback(
    ctx: click.Context,
    param: click.Parameter,
    value: str,
) -> None:
    """Set the log level."""
    if ctx.resilient_parsing:
        return
    reset_logger(level=value, verbose=False)
    logger.debug(f"reset logger: level={value}")


class _Group(typer.core.TyperGroup):
    @override
    def get_params(self, ctx: Any) -> list[Any]:
        """Get command parameters with added global options.

        Extends base parameters with --help_all and --log_level options.

        Parameters
        ----------
        ctx : click.Context
            Click context for the command

        Returns
        -------
        list[click.Parameter]
            List of command parameters including global options
        """
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
            type=click.Choice(["DEBUG", "INFO", "WARNING"]),
            default="INFO",
            show_default=True,
            callback=_reset_logger_callback,
            help="Set the log level.",
            is_eager=True,
        )
        params.extend([help_all_opt, log_level_opt])
        return params

    @override
    def invoke(self, ctx: Any) -> Any:
        """Invoke command with cleaned parameters.

        Removes global options (help_all, log_level) from context before
        invoking the actual command.

        Parameters
        ----------
        ctx : click.Context
            Click context with command parameters

        Returns
        -------
        Any
            Result from invoking the command
        """
        for pname in ["help_all", "log_level"]:
            if pname in ctx.params:
                del ctx.params[pname]
        return super().invoke(ctx)


class _MultiValueCommand(typer.core.TyperCommand):
    """A Typer command that expands one variadic option into repeated options.

    Click natively supports repeatable list options but not ``nargs=-1`` for an
    option. This command preserves Tollan's ``--option a b c`` syntax by
    normalizing it to ``--option a --option b --option c`` before delegating to
    Click's public ``Command.parse_args`` implementation. Typer therefore keeps
    ownership of type conversion, validation, help, and callbacks.
    """

    @staticmethod
    def _is_option_token(value: str) -> bool:
        return value == "--" or (len(value) > 1 and value.startswith("-"))

    def _multi_option_flags(self) -> set[str]:
        callback = self.callback
        if callback is None:
            return set()
        param_meta = get_params_from_function(callback)
        multi_names = {
            name
            for name, meta in param_meta.items()
            if isinstance(meta.default, MultiOptionInfo)
        }
        return {
            flag
            for param in self.params
            if isinstance(param, typer.core.TyperOption) and param.name in multi_names
            for flag in (*param.opts, *param.secondary_opts)
        }

    @classmethod
    def _expand_multi_options(
        cls,
        args: list[str],
        multi_flags: set[str],
    ) -> list[str]:
        result: list[str] = []
        index = 0
        while index < len(args):
            token = args[index]
            option_flag, has_inline_value, _ = token.partition("=")
            if option_flag not in multi_flags:
                result.append(token)
                index += 1
                continue

            result.append(token)
            index += 1
            has_value = bool(has_inline_value)
            while index < len(args) and not cls._is_option_token(args[index]):
                if has_value:
                    result.append(option_flag)
                result.append(args[index])
                has_value = True
                index += 1
        return result

    @override
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        """Normalize Tollan multi-options, then use Click's parser."""
        flags = self._multi_option_flags()
        if flags:
            args = self._expand_multi_options(args, flags)
        return super().parse_args(ctx, args)


class TollanTyper(typer.Typer):
    """Typer application with Tollan's command-local CLI extensions."""

    def command(self, name: str | None = None, **kwargs: Any) -> Callable:
        """Register a command using Tollan's parser without global patches."""
        command_kwargs = dict(kwargs)
        command_kwargs.setdefault("cls", _MultiValueCommand)

        def decorator(callback: Callable) -> Callable:
            # Preserve Tollan's historical underscore command names locally.
            command_name = name if name is not None else cast("Any", callback).__name__
            parent_decorator = super(TollanTyper, self).command(
                command_name,
                **command_kwargs,
            )
            return parent_decorator(callback)

        return decorator


# =============================================================================
# MultiOption Integration
# =============================================================================


class MultiOptionInfo(OptionInfo):
    """Extended OptionInfo for multi-argument options.

    This class marks an option for preprocessing by :class:`TollanTyper`.

    Parameters
    ----------
    option_info : OptionInfo
        The base OptionInfo created by typer.Option()
    """

    is_multi_option: bool = True

    def __init__(self, option_info: OptionInfo) -> None:
        """Initialize MultiOptionInfo from base OptionInfo."""
        # Copy all fields from base OptionInfo
        super().__init__(**option_info.__dict__)


def MultiOption(  # noqa: N802
    default: Any = ...,
    *param_decls: str,
    **kwargs: Any,
) -> MultiOptionInfo:
    """Create a multi-argument option for Typer commands.

    This function wraps :func:`typer.Option` metadata so :class:`TollanTyper`
    can accept multiple values in a single invocation. No global Typer state is
    modified.

    Parameters
    ----------
    default : Any, default=...
        Default value for the option
    *param_decls : str
        Parameter declarations (e.g., "--files", "-f")
    **kwargs : Any
        All other arguments passed to typer.Option() (help, exists, etc.)

    Returns
    -------
    MultiOptionInfo
        Extended OptionInfo with multi-option flag

    Examples
    --------
    >>> from typing import Annotated
    >>> from pathlib import Path
    >>> import typer
    >>> from tollan.utils.typer import MultiOption
    >>>
    >>> from tollan.utils.typer import TollanTyper
    >>> app = TollanTyper()
    >>>
    >>> @app.command()
    ... def process(
    ...     files: Annotated[
    ...         list[Path] | None,
    ...         MultiOption(
    ...             help="Files to process",
    ...             exists=True,
    ...             dir_okay=False,
    ...         ),
    ...     ] = None,
    ... ):
    ...     '''Process multiple files.'''
    ...     if files:
    ...         for f in files:
    ...             typer.echo(f"Processing: {f}")
    >>>
    >>> # $ python main.py process --files file1.txt file2.txt file3.txt
    >>> # Processing: file1.txt
    >>> # Processing: file2.txt
    >>> # Processing: file3.txt
    """
    # Let typer.Option handle all the complex parameter processing
    option_info = typer.Option(default, *param_decls, **kwargs)

    # Wrap in MultiOptionInfo with our flag
    return MultiOptionInfo(option_info)
