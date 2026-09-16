"""Typer option adapters for runtime configuration."""

from __future__ import annotations

import inspect
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import typer

from ..utils.typer import MultiOption

if TYPE_CHECKING:
    from collections.abc import Callable


def _add_cli_options(func: Callable) -> Callable:
    """Add path options while leaving runtime construction to the callback."""
    signature = inspect.signature(func, eval_str=True)
    parameters = signature.parameters
    reserved = {"config_paths", "env_paths", "_runtime_ctx"} & parameters.keys()
    if reserved:
        msg = f"Runtime options own these parameters: {sorted(reserved)}"
        raise TypeError(msg)
    ctx_name = next(
        (p.name for p in parameters.values() if p.annotation is typer.Context),
        "_runtime_ctx",
    )
    parameters_cli = list(parameters.values())
    if ctx_name == "_runtime_ctx":
        parameters_cli.append(
            inspect.Parameter(
                ctx_name, inspect.Parameter.KEYWORD_ONLY, annotation=typer.Context
            )
        )
    for option, aliases, help_text in (
        (
            "config_paths",
            ("-c",),
            "Config files or directories, in increasing precedence.",
        ),
        ("env_paths", (), "Dotenv files or directories, in increasing precedence."),
    ):
        parameters_cli.append(
            inspect.Parameter(
                option,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=list[Path] | None,
                default=MultiOption(
                    None, f"--{option}", *aliases, exists=True, help=help_text
                ),
            )
        )

    @wraps(func)
    def invoke(**kwargs: Any) -> Any:
        ctx = kwargs[ctx_name]
        # Click's ctx.params still contains raw tuples of strings. Save Typer's
        # converted Path lists so from_cli_ctx receives the same typed values
        # that an explicitly declared option parameter would receive.
        for name in ("config_paths", "env_paths"):
            ctx.params[name] = kwargs.pop(name)
        if ctx_name == "_runtime_ctx":
            kwargs.pop(ctx_name)
        return func(**kwargs)

    cast("Any", invoke).__signature__ = signature.replace(parameters=parameters_cli)
    # Resolve annotations in the user's namespace before Typer inspects the
    # wrapper, whose globals belong to this module.
    invoke.__annotations__ = {
        p.name: p.annotation
        for p in parameters_cli
        if p.annotation is not inspect.Parameter.empty
    }
    return invoke
