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


class MultiActionArgumentParser(wrapt.ObjectProxy):
    """This class wraps the `argparse.ArgumentParser` so that it
    allows defining subcommands with ease."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('add_help', False)
        self._self_parser = p = argparse.ArgumentParser(*args, **kwargs)
        super().__init__(self._self_parser)

        p.add_argument(
            '-h', '--help', action=RecursiveHelpAction,
            help='Show this (and more) help message and exit')
        self._self_action_parser_group = self.add_subparsers(
                title="actions",
                help="Available actions"
                )

    def add_action_parser(self, *args, **kwargs):
        p = self._self_action_parser_group.add_parser(*args, **kwargs)
        # patch the action parser with method
        p.parser_action = self.parser_action(p)
        return p

    @staticmethod
    def parser_action(parser):
        def decorator(action):
            parser.set_defaults(func=action)
            return action
        return decorator

    def bootstrap_actions(self, option):
        if hasattr(option, 'func'):
            option.func(option)
        else:
            self.print_help()
