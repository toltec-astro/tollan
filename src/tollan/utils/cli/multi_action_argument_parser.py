import argparse

import wrapt

__all__ = [
    "MultiActionArgumentParser",
]


try:
    from mpi4py import MPI as _MPI
except ModuleNotFoundError:
    _MPI = None


class RecursiveHelpAction(argparse._HelpAction):
    @staticmethod
    def _indent(text, prefix, predicate=None):
        """Adds 'prefix' to the beginning of selected lines in 'text'.
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

    def __call__(self, parser, namespace, values, option_string=None):
        parser.print_help()
        # retrieve subparsers from parser
        subparsers_actions = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        print("")
        for subparsers_action in subparsers_actions:
            # get all subparsers and print help
            for choice, subparser in subparsers_action.choices.items():
                print("{}:".format(choice))
                print(self._indent(subparser.format_help(), "  "))
        parser.exit()


class _SubParsersAction(argparse._SubParsersAction):
    def __call__(self, parser, namespace, values, option_string=None):
        # this is to fix that '--' is picked up as action.
        if values[0] == "--":
            values = values[1:]
        super().__call__(parser, namespace, values, option_string=option_string)


class ArgumentParser(argparse.ArgumentParser):
    def _check_value(self, action, value):
        # this is to by-pass the validation of '--'
        # converted value must be one of the choices (if specified)
        if action.nargs == argparse.PARSER and value == "--":
            return
        super()._check_value(action, value)


class MultiActionArgumentParser(wrapt.ObjectProxy):
    """This class wraps the `argparse.ArgumentParser` so that it
    allows defining subcommands with ease."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("add_help", False)
        p = self._self_parser = ArgumentParser(*args, **kwargs)
        super().__init__(self._self_parser)

        p.register("action", "parsers", _SubParsersAction)
        p.add_argument(
            "-h",
            "--help",
            action=RecursiveHelpAction,
            help="Show the full help message and exit.",
        )
        self._self_action_parser_group = self.add_subparsers(
            title="actions", help="Available actions."
        )

    def add_action_parser(self, *args, action=None, mpi_passthrough=False, **kwargs):
        """Return a new action parser.

        An action parser has an attached `parser_action` decorator that can
        wrap a custom function to be executed when required via the commandline.

        Parameters
        ----------
        action : callable, optional
            The action to take when requested on commandline.
        mpi_passthrough : bool, optional
            When set to True, the action is invoked in all ranks when MPI is used.
        """
        p = self._self_action_parser_group.add_parser(add_help=False, *args, **kwargs)
        p.add_argument(
            "-h",
            "--help",
            action="help",
            default=argparse.SUPPRESS,
            help="Show help for this subcommand and exit.",
        )
        # patch the action parser with method
        parser_action = p.parser_action = self.parser_action(
            p, mpi_passthrough=mpi_passthrough
        )
        # set the action if provided
        if action is not None:
            parser_action(action)
        return p

    def register_action_parser(self, *args, **kwargs):
        """A helper decorator to create and setup an action parser in one go."""

        def decorator(func):
            act = self.add_action_parser(*args, **kwargs)
            func(act)

        return decorator

    @staticmethod
    def parser_action(parser, mpi_passthrough=False):
        """Return a decorator that wraps"""

        def decorator(action):
            if mpi_passthrough or _MPI is None:
                _action = action
            else:
                # here we only attach action to rank 0
                comm = _MPI.COMM_WORLD
                rank = comm.Get_rank()
                if rank == 0:
                    _action = action
                else:
                    _action = None
            parser.set_defaults(_action=_action)
            return action

        return decorator

    def bootstrap_actions(self, option, unknown_args=None):
        print(option)
        if hasattr(option, "_action"):
            action = option._action
            if action is not None:
                action(option, unknown_args=unknown_args)
        else:
            self.print_help()
