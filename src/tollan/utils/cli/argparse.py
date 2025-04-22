import argparse
import dataclasses
from collections.abc import Callable
from typing import TypedDict

from tollan.utils.log import logger, reset_logger

__all__ = [
    "MultiActionCli",
]


try:
    from mpi4py import MPI as _MPI  # type: ignore
except ModuleNotFoundError:
    _MPI = None


class RecursiveHelpAction(argparse._HelpAction):  # noqa: SLF001
    """An action class to work with recursive help commands."""

    @staticmethod
    def _indent(text, prefix, predicate=None):
        """Add 'prefix' to the beginning of selected lines in 'text'.

        If 'predicate' is provided, 'prefix' will only be added to the lines
        where 'predicate(line)' is True. If 'predicate' is not provided,
        it will default to adding 'prefix' to all non-empty lines that do not
        consist solely of whitespace characters.
        """
        if predicate is None:

            def _predicate(line):
                return line.strip()

        else:
            _predicate = predicate

        def prefixed_lines():
            for line in text.splitlines(True):
                yield (prefix + line if _predicate(line) else line)

        return "".join(prefixed_lines())

    def __call__(
        self,
        parser,
        _namespace,
        _values,
        _option_string=None,
    ):
        parser.print_help()
        # retrieve subparsers from parser
        subparsers_actions = [
            action
            for action in parser._actions  # noqa: SLF001
            if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
        ]
        _print = parser._print_message  # noqa: SLF001
        _print("\nsubcommand details:\n\n")
        for subparsers_action in subparsers_actions:
            # get all subparsers and print help
            for choice, subparser in subparsers_action.choices.items():
                _print(f"{choice}:")
                _print(self._indent(subparser.format_help(), "  "))
        parser.exit()


class _SubParsersAction(argparse._SubParsersAction):  # noqa: SLF001
    def __call__(self, parser, namespace, values, option_string=None):
        # this is to fix that '--' is picked up as action.
        if values is not None and values[0] == "--":
            values = values[1:]
        super().__call__(parser, namespace, values, option_string=option_string)


class ArgumentParser(argparse.ArgumentParser):
    """A subclass of argument parser to handle the separator `--`."""

    def _check_value(self, action, value):
        # this is to by-pass the validation of '--'
        # converted value must be one of the choices (if specified)
        if action.nargs == argparse.PARSER and value == "--":
            return
        super()._check_value(action, value)


@dataclasses.dataclass
class MultiActionCli:
    """A CLI entry point class with reasonable defaults."""

    class _RegInfo(TypedDict):
        args: tuple
        kwargs: dict
        callback: None | Callable
        post_init: Callable[..., ArgumentParser]

    @staticmethod
    def _make_parser_def(args, kwargs, callback, post_init) -> _RegInfo:
        """Return the bits for creating parser."""
        if not args:
            args = (post_init.__name__,)
        kwargs.setdefault("help", post_init.__doc__ or callback.__doc__)
        return {
            "args": args,
            "kwargs": kwargs,
            "callback": callback,
            "post_init": post_init,
        }

    _main_parser_def: None | _RegInfo = dataclasses.field(
        default=None,
        init=False,
        repr=False,
    )
    _action_parser_defs: dict[str, _RegInfo] = dataclasses.field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    version: str = "dev"

    def register_main(self, *args, callback=None, **kwargs):
        """Register the main parser."""

        def decorator(func):
            self._main_parser_def = self._make_parser_def(
                args=args,
                kwargs=kwargs,
                callback=callback,
                post_init=func,
            )
            return func

        return decorator

    def register_action(self, *args, callback=None, **kwargs):
        """Register a new action parser."""

        def decorator(func):
            key = args[0]
            if key in self._action_parser_defs:
                raise ValueError(f"Action {key} is already registered.")
            self._action_parser_defs[key] = self._make_parser_def(
                args=args,
                kwargs=kwargs,
                callback=callback,
                post_init=func,
            )
            return func

        return decorator

    def bootstrap_parsers(self):
        """Create the main parser and subparsers."""
        if self._main_parser_def is None:
            raise ValueError("no main is registered.")
        args = self._main_parser_def["args"]
        kwargs = self._main_parser_def["kwargs"]
        post_init = self._main_parser_def["post_init"]
        # handle alias for `description` for the main parser
        if "help" in kwargs:
            kwargs["description"] = kwargs.pop("help")
        p = main_parser = ArgumentParser(*args, **kwargs)
        p.register("action", "parsers", _SubParsersAction)
        g = p.add_subparsers(
            title="actions",
            help="Available actions.",
        )
        p.add_argument(
            "--help_all",
            action=RecursiveHelpAction,
            help="Show full help and exit.",
        )
        p.add_argument(
            "--log_level",
            "-l",
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING"],
            help="Set the log level.",
        )
        p.add_argument("--version", "-v", action="version", version=self.version)

        post_init(p)

        def _make_action_func(func, mpi_passthrough):
            if mpi_passthrough or _MPI is None:
                _action = func
            else:
                # here we only attach action to rank 0
                comm = _MPI.COMM_WORLD
                rank = comm.Get_rank()
                _action = func if rank == 0 else None
            return _action

        if not self._action_parser_defs:
            raise ValueError("no action is registered.")

        for parser_def in self._action_parser_defs.values():
            args = parser_def["args"]
            kwargs = parser_def["kwargs"]
            callback = parser_def["callback"]
            post_init = parser_def["post_init"]
            mpi_passthrough = kwargs.pop("mpi_passthrough", False)
            p = g.add_parser(*args, add_help=False, **kwargs)
            p.add_argument(
                "-h",
                "--help",
                action="help",
                default=argparse.SUPPRESS,
                help="Show help for this subcommand and exit.",
            )
            # handle action func
            p.set_defaults(
                _action=_make_action_func(
                    callback,
                    mpi_passthrough=mpi_passthrough,
                ),
            )
            post_init(p)
        return main_parser

    def __call__(self, args=None):
        """Invoke the CLI."""
        parser = self.bootstrap_parsers()
        option, unknown_args = parser.parse_known_args(args)
        log_level = option.log_level
        reset_logger(level=log_level, verbose=False)
        logger.debug(f"reset logger: level={log_level}")
        # handle the main callback
        callback = self._main_parser_def["callback"]
        if callback is not None:
            callback(parser)
        logger.debug(f"bootstrap actions: {option=}")
        if hasattr(option, "_action"):
            action = option._action  # noqa: SLF001
            if action is not None:
                action(option, unknown_args=unknown_args)
        else:
            parser.print_help()
        return 0
