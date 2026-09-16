"""Typer CLI utility functions.

This module extends Typer's CLI functionality with custom options and utilities.
The main feature is MultiOption, which enables variable-length option arguments
in Typer commands, with automatic type conversion via Typer's built-in system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast, override

from rich.console import Console
from rich.rule import Rule

if TYPE_CHECKING:
    from collections.abc import Callable


import typer
import typer.core
import typer.main
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
    """Create an application with a version command, help, and logging options.

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
    ctx: typer.Context,
    param: typer.core.TyperOption,
    value: bool,  # noqa: FBT001
) -> None:
    """Show full help for this group and its immediate children, then exit."""
    if not value or ctx.resilient_parsing:
        return

    def print_help(context: Any) -> None:
        # Match Typer's regular --help rendering, including its color policy.
        typer.echo(context.get_help(), color=context.color)

    console = Console()
    print_help(ctx)
    if isinstance(ctx.command, typer.core.TyperGroup):
        for name, command in ctx.command.commands.items():
            # Do not parse children: help must not require their inputs or
            # execute parameter callbacks. The parent supplies the usage path.
            with command.context_class(
                command, info_name=name, parent=ctx, **command.context_settings
            ) as child_context:
                console.print()
                console.print(
                    Rule(
                        f"Command: {child_context.command_path}",
                        style="blue",
                        align="left",
                    )
                )
                print_help(child_context)
    raise typer.Exit(code=0)


def _reset_logger_callback(
    ctx: typer.Context,
    param: typer.core.TyperOption,
    value: str | None,
) -> None:
    """Apply an explicit log level, or initialize INFO without an inherited level."""
    if ctx.resilient_parsing:
        return
    if value is None:
        parent = ctx.parent
        while parent is not None:
            # Tollan handles its option without exposing it in params. A regular
            # Typer ancestor can also own a log_level parameter and configure
            # logging itself; do not replace that setting with our fallback.
            if (
                isinstance(parent.command, _Group)
                or parent.params.get("log_level") is not None
            ):
                return
            parent = parent.parent
        value = "INFO"
    reset_logger(level=value, verbose=False)
    logger.debug(f"reset logger: level={value}")


def _preserve_option_names(
    command: typer.core.TyperCommand | typer.core.TyperGroup,
) -> None:
    """Keep Python names for inferred options; preserve explicit declarations."""
    # Typer has no app-level naming hook (fastapi/typer discussion #1049).
    # Commands and groups are built separately, so both constructors call this.
    if command.callback is None:
        return
    metadata = get_params_from_function(command.callback)
    for param in command.params:
        if not isinstance(param, typer.core.TyperOption) or param.name not in metadata:
            continue
        default = metadata[param.name].default
        if isinstance(default, OptionInfo) and default.param_decls:
            continue
        param.opts = [f"--{param.name}"]
        if param.secondary_opts:
            param.secondary_opts = [f"--no_{param.name}"]


class _Group(typer.core.TyperGroup):
    """Tollan group with Python names, multi-options, help, and logging."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _preserve_option_names(self)

    @override
    def get_params(self, ctx: Any) -> list[Any]:
        """Add help and logging options at every Tollan group.

        Both options are handled internally, not passed to group callbacks.
        An omitted log level inherits an ancestor's setting, falling back to INFO.
        """
        params = list(super().get_params(ctx))
        params.extend(
            [
                typer.core.TyperOption(
                    param_decls=["--help_all"],
                    type=bool,
                    is_flag=True,
                    show_default=False,
                    callback=_help_all_callback,
                    help=_help_all_callback.__doc__,
                    is_eager=True,
                    expose_value=False,
                ),
                typer.core.TyperOption(
                    param_decls=["--log_level", "-l"],
                    # Let Typer build its own choice type, not external Click's.
                    type=typer.main.get_click_type(
                        annotation=Literal["DEBUG", "INFO", "WARNING"],
                        parameter_info=OptionInfo(),
                    ),
                    default=None,
                    show_default="inherited, otherwise INFO",
                    callback=_reset_logger_callback,
                    help="Set the log level, overriding an ancestor's setting.",
                    is_eager=True,
                    expose_value=False,
                ),
            ]
        )
        return params

    @override
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        """Expand group multi-options without rewriting the child command's argv."""
        return super().parse_args(ctx, _MultiOptionParser(self).parse_args(ctx, args))


class _MultiOptionParser:
    """Normalize variadic options for a Typer command or group."""

    def __init__(
        self, command: typer.core.TyperCommand | typer.core.TyperGroup
    ) -> None:
        self.command = command

    @staticmethod
    def _is_option_token(value: str) -> bool:
        return value == "--" or (len(value) > 1 and value.startswith("-"))

    def _multi_option_flags(self) -> set[str]:
        callback = self.command.callback
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
            for param in self.command.params
            if isinstance(param, typer.core.TyperOption) and param.name in multi_names
            for flag in (*param.opts, *param.secondary_opts)
        }

    @classmethod
    def _expand_multi_options(
        cls,
        args: list[str],
        multi_flags: set[str],
        *,
        option_nargs: dict[str, int],
        is_group: bool,
    ) -> list[str]:
        result: list[str] = []
        index = 0
        while index < len(args):
            arg = args[index]
            # A separator ends option parsing. A group's first positional
            # argument starts the child command; its argv belongs to that child.
            if arg == "--" or (is_group and not arg.startswith("-")):
                result.extend(args[index:])
                break
            option_flag, has_inline_value, _ = arg.partition("=")
            if option_flag not in multi_flags:
                result.append(arg)
                index += 1
                # Ordinary options still own their declared number of values.
                # Do not mistake those values for another option or a child name.
                nargs = 0 if has_inline_value else option_nargs.get(option_flag, 0)
                result.extend(args[index : index + nargs])
                index += nargs
                continue

            result.append(arg)
            index += 1
            has_value = bool(has_inline_value)
            while index < len(args) and not cls._is_option_token(args[index]):
                if has_value:
                    result.append(option_flag)
                result.append(args[index])
                has_value = True
                index += 1
        return result

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        """Return normalized arguments without converting or validating values."""
        flags = self._multi_option_flags()
        if not flags:
            return args
        option_nargs = {
            flag: param.nargs
            for param in self.command.get_params(ctx)
            if isinstance(param, typer.core.TyperOption)
            and not param.is_flag
            and not param.count
            for flag in (*param.opts, *param.secondary_opts)
        }
        return self._expand_multi_options(
            args,
            flags,
            option_nargs=option_nargs,
            is_group=isinstance(self.command, typer.core.TyperGroup),
        )


class _Command(typer.core.TyperCommand):
    """Tollan command with Python names and multi-value options."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _preserve_option_names(self)

    @override
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        """Expand multi-options, then delegate conversion and validation to Typer."""
        return super().parse_args(ctx, _MultiOptionParser(self).parse_args(ctx, args))


class TollanTyper(typer.Typer):
    """Typer application with Python names and multi-value options.

    Command and option names follow their Python names unless explicitly named.
    Use :func:`MultiOption` to accept several values for an option.

    Groups provide ``--help_all`` to show their own help and their direct
    children's help, and ``--log_level`` to select DEBUG, INFO, or WARNING.
    Nested groups inherit the selected log level unless overridden. The default
    level is INFO.

    Examples
    --------
    >>> app = TollanTyper()
    >>> @app.command()
    ... def say_hello(user_name: str = "world"):
    ...     print(f"Hello, {user_name}!")
    >>> # python app.py --user_name Alice
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cls", _Group)
        super().__init__(**kwargs)

    def command(self, name: str | None = None, **kwargs: Any) -> Callable:
        """Register a command, using its Python function name by default."""
        kwargs.setdefault("cls", _Command)

        def decorator(callback: Callable) -> Callable:
            command_name = name if name is not None else cast("Any", callback).__name__
            return super(TollanTyper, self).command(command_name, **kwargs)(callback)

        return decorator


# =============================================================================
# MultiOption Integration
# =============================================================================


class MultiOptionInfo(OptionInfo):
    """Extended OptionInfo for multi-argument options.

    Option metadata returned by :func:`MultiOption`.

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

    Accept several values after one option flag, or repeat the flag to add more
    values. Values are converted and validated according to the parameter's
    annotation and the supplied :func:`typer.Option` arguments. Use ``--``
    to separate subsequent positional arguments.

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
    >>> from tollan.utils.typer import MultiOption, TollanTyper
    >>>
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
