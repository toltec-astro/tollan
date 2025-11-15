"""Typer CLI utility functions.

This module extends Typer's CLI functionality with custom options and utilities.
The main feature is MultiOption, which enables variable-length option arguments
in Typer commands, with automatic type conversion via Typer's built-in system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from rich.console import Console
from rich.rule import Rule

if TYPE_CHECKING:
    from collections.abc import Callable

    from typer.models import ParamMeta

import click
import typer
import typer.core
import typer.main
from typer.models import OptionInfo

from .log import logger, reset_logger

__all__ = [
    "MultiOption",
    "MultiOptionInfo",
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
    # HACK: Disable automatic conversion of underscores to dashes in CLI option names.
    # By default, typer converts snake_case parameter names (e.g., env_files) to
    # kebab-case CLI options (e.g., --env-file). This can be confusing and inconsistent
    # with Python naming conventions. This override keeps parameter names as-is.
    # See: https://github.com/fastapi/typer/discussions/1049
    # Note: This affects both option names AND command names.
    typer.main.get_command_name = lambda name: name  # ty: ignore[invalid-assignment]

    # Set reasonable defaults, allowing caller to override
    typer_kwargs: dict[str, Any] = {
        "context_settings": {"help_option_names": ["-h", "--help"]},
        "cls": _Group,
    }
    typer_kwargs.update(kwargs)

    app = typer.Typer(**typer_kwargs)

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
    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
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
    def invoke(self, ctx: click.Context) -> Any:
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


class _OptionEatAll(typer.core.TyperOption):
    """Typer Option that consumes all arguments until the next option.

    This class provides variable-length option arguments (nargs='*' equivalent)
    by consuming all remaining arguments until another option flag or the '--'
    separator is encountered. This is a workaround for Click's limitation that
    options only support fixed number of arguments.

    Parameters
    ----------
    *args : Any
        Positional arguments passed to click.Option
    **kwargs : Any
        Keyword arguments passed to click.Option (nargs will be forced to -1)

    Notes
    -----
    This implementation is adapted from the Click/Typer community workaround.
    See: https://github.com/fastapi/typer/issues/110#issuecomment-3386589706

    This class is used internally by MultiOption. Typer handles type conversion
    automatically via generate_list_convertor().

    See Also
    --------
    MultiOption : High-level Typer interface for multi-argument options
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize OptionEatAll with validation.

        Parameters
        ----------
        *args : Any
            Positional arguments for click.Option
        **kwargs : Any
            Keyword arguments for click.Option
        """
        nargs = kwargs.pop("nargs", -1)
        if nargs != -1:
            msg = f"nargs must be -1, not {nargs}"
            raise AssertionError(msg)
        # Force multiple=True and is_flag=False for proper value handling
        kwargs["multiple"] = True
        kwargs["is_flag"] = False
        super().__init__(*args, **kwargs)
        self._previous_parser_process: Callable[..., Any] | None = None
        self._eat_all_parser: Any = None

    @override
    def add_to_parser(self, parser: Any, ctx: click.Context) -> Any:
        """Add this option to the parser with custom processing logic.

        Parameters
        ----------
        parser : Any
            Click parser instance
        ctx : click.Context
            Click context

        Returns
        -------
        Any
            Result from parent add_to_parser
        """

        def parser_process(value: str, state: Any) -> None:
            """Process arguments, consuming multiple values.

            Parameters
            ----------
            value : str
                First value after the option flag
            state : Any
                Parser state containing remaining arguments
            """
            done = False
            values = [value]

            # Consume arguments until we hit another option flag
            while state.rargs and not done:
                for prefix in self._eat_all_parser.prefixes:
                    if state.rargs[0].startswith(prefix):
                        done = True
                        break
                if not done:
                    values.append(state.rargs.pop(0))

            # Call the original process method for each value individually
            # This allows Click's multiple=True to accumulate them properly
            assert self._previous_parser_process is not None
            for val in values:
                self._previous_parser_process(val, state)

        # Add option to parser using parent method
        retval = super().add_to_parser(parser, ctx)

        # Find our parser and monkey-patch its process method
        for name in self.opts:
            our_parser = parser._long_opt.get(name) or parser._short_opt.get(name)
            if our_parser:
                self._eat_all_parser = our_parser
                self._previous_parser_process = our_parser.process
                our_parser.process = parser_process
                break

        return retval


# =============================================================================
# MultiOption Integration
# =============================================================================


class MultiOptionInfo(OptionInfo):
    """Extended OptionInfo for multi-argument options.

    This class extends Typer's OptionInfo to add a flag indicating that this
    option should use the OptionEatAll Click option class instead of the
    default TyperOption class.

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

    This function wraps typer.Option() to create options that can accept
    multiple values in a single invocation. It returns a MultiOptionInfo
    instance that will be detected by the patched get_click_param function
    to create an OptionEatAll Click option.

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
    >>> app = typer.Typer()
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


# Save original get_click_param before monkey-patching
_original_get_click_param = typer.main.get_click_param


def _patched_get_click_param(
    param: ParamMeta,
) -> tuple[click.Parameter, Any]:
    """Patched version of get_click_param that detects MultiOptionInfo.

    This function wraps the original typer.main.get_click_param to detect
    when a parameter uses MultiOptionInfo and creates an OptionEatAll
    Click option instead of the default TyperOption.

    Parameters
    ----------
    param : ParamMeta
        Parameter metadata from function signature inspection

    Returns
    -------
    tuple[click.Parameter, Any]
        (Click parameter, value converter function)
    """
    # Call original to get the TyperOption and converter
    click_param, converter = _original_get_click_param(param)

    # Check if this is a MultiOptionInfo (only applies to Options, not Arguments)
    if isinstance(param.default, MultiOptionInfo):
        assert isinstance(click_param, click.Option), (
            "MultiOption only works with Options, not Arguments"
        )

        # Create an OptionEatAll instance without calling __init__
        # Then copy all state from the TyperOption that Typer configured
        option_eat_all = object.__new__(_OptionEatAll)
        option_eat_all.__dict__.update(click_param.__dict__)

        # Initialize the OptionEatAll-specific attributes that __init__ would have set
        option_eat_all._previous_parser_process = None
        option_eat_all._eat_all_parser = None

        return (option_eat_all, converter)

    # Not a MultiOption, return original result
    return (click_param, converter)


# Install the monkey-patch
typer.main.get_click_param = _patched_get_click_param  # ty: ignore[invalid-assignment]
