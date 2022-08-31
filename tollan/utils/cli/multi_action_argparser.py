#! /usr/bin/env python

import argparse
import wrapt


__all__ = ['MultiActionArgumentParser', ]


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
            def predicate(line):
                return line.strip()

        def prefixed_lines():
            for line in text.splitlines(True):
                yield (prefix + line if predicate(line) else line)
        return ''.join(prefixed_lines())

    def __call__(self, parser, namespace, values, option_string=None):
        parser.print_help()
        # retrieve subparsers from parser
        subparsers_actions = [
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)]
        # there will probably only be one subparser_action,
        # but better save than sorry
        print("")
        for subparsers_action in subparsers_actions:
            # get all subparsers and print help
            for choice, subparser in subparsers_action.choices.items():
                print('{}:'.format(choice))
                print(self._indent(subparser.format_help(), '  '))
        parser.exit()


class _SubParsersAction(argparse._SubParsersAction):

    def __call__(self, parser, namespace, values, option_string=None):
        # this is to fix that '--' is picked up as action.
        if values[0] == '--':
            values = values[1:]
        super().__call__(
                parser, namespace, values, option_string=option_string)


class ArgumentParser(argparse.ArgumentParser):

    def _check_value(self, action, value):
        # this is to by-pass the validation of '--'
        # converted value must be one of the choices (if specified)
        if action.nargs == argparse.PARSER and value == '--':
            return
        super()._check_value(action, value)


class MultiActionArgumentParser(wrapt.ObjectProxy):
    """This class wraps the `argparse.ArgumentParser` so that it
    allows defining subcommands with ease."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('add_help', False)
        self._self_parser = p = ArgumentParser(*args, **kwargs)
        super().__init__(self._self_parser)

        p.register('action', 'parsers', _SubParsersAction)
        p.add_argument(
            '-h', '--help', action=RecursiveHelpAction,
            help='Show the full help message and exit.')
        self._self_action_parser_group = self.add_subparsers(
                title="actions",
                help="Available actions."
                )

    def add_action_parser(self, *args, mpi_passthrough=False, **kwargs):
        p = self._self_action_parser_group.add_parser(
                add_help=False,
                *args, **kwargs)
        p.add_argument(
                '-h', '--help', action='help', default=argparse.SUPPRESS,
                help='Show help for this subcommand and exit.')
        # patch the action parser with method
        p.parser_action = self.parser_action(
            p, mpi_passthrough=mpi_passthrough)
        return p

    def register_action_parser(self, *args, **kwargs):

        def decorator(func):
            act = self.add_action_parser(*args, **kwargs)
            func(act)
        return decorator

    @staticmethod
    def parser_action(parser, mpi_passthrough=False):
        def decorator(action):
            if mpi_passthrough:
                func = action
            else:
                # we return an no-op action for worker ranks
                try:
                    from mpi4py import MPI
                    comm = MPI.COMM_WORLD
                    rank = comm.Get_rank()
                    if rank == 0:
                        func = action
                    else:
                        def func(*a, **k):
                            return
                except ModuleNotFoundError:
                    func = action
            parser.set_defaults(func=func)
            return action
        return decorator

    def bootstrap_actions(self, option, unknown_args=None):
        print(option)
        if hasattr(option, 'func'):
            option.func(option, unknown_args=unknown_args)
        else:
            self.print_help()
