#! /usr/bin/env python

import argparse


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


def get_action_argparser(**kwargs):
    parser = argparse.ArgumentParser(
        add_help=False,
        **kwargs
        )
    parser.add_argument(
            '-h', '--help', action=RecursiveHelpAction,
            help='show this (and more) help message and exit')
    action_parser = parser.add_subparsers(
            title="actions",
            help="available actions")

    def set_parser_action(parser):
        def decorator(func):
            parser.set_defaults(func=func)
            return func
        return decorator

    def add_action_parser(*args, **kwargs):
        return action_parser.add_parser(*args, **kwargs)

    return parser, add_action_parser, set_parser_action
