"""A subpackage that provides CLI utilties."""

import argparse
import re

from ..fmt import pformat_yaml
from ..general import dict_from_flat_dict
from ..log import logger
from ..yaml import yaml_loads

__all__ = ["split_cli_args", "dict_from_cli_args"]


_re_arg = re.compile(r"^--(?P<key>[a-zA-Z_]([a-zA-z0-9_.\[\]+])*)")


def split_cli_args(re_name, args):
    """Split the args based on regex match of the arg name."""
    matched = []
    unmatched = []
    positional_key = "--"
    re_name = re.compile(re_name)
    store = unmatched
    args = list(map(str, args))
    arg_pending_value = False
    for arg in args:
        if arg == positional_key:
            unmatched.append(arg)
            arg_pending_value = False
            continue
            # anything beyond the -- is marked positional and is unmatched
            # unmatched.extend(args[i:])
            # break
        m = _re_arg.fullmatch(arg)
        if m is None:
            if arg_pending_value:
                store.append(arg)
            else:
                # free floating value is always unmatched
                unmatched.append(arg)
            arg_pending_value = False
            continue
        mn = re_name.fullmatch(m.groupdict()["key"])
        store = unmatched if mn is None else matched
        store.append(arg)
        arg_pending_value = True
    return matched, unmatched


def dict_from_cli_args(args):
    """Return a nested dict composed from CLI arguments.

    This is useful to compose nested dict from flag. Nested keys can
    be specified using syntax like ``--a.b.c``. Nested lists are
    supported with the index as the key: ``--a.0.c``. The values
    of the options are parsed as YAML string.
    """
    logger.debug(f"parse command line args: {args}")

    parser = argparse.ArgumentParser()
    n_args = len(args)
    known_args = set()
    args = list(map(str, args))
    for i, arg in enumerate(args):
        # collect all items that are argument keys.
        m = _re_arg.match(arg)
        if m is None:
            continue
        val = args[i + 1] if i + 1 < n_args else None
        # parse the item with config yaml loader
        arg_kwargs = {
            "type": yaml_loads,
            "required": True,
        }
        if val is None or _re_arg.match(val) is not None:
            # the next item is a validate arg, this is a flag
            # inorder to allow overriting flag, we make this
            # a boolean switch with defautl = True nargs=?
            arg_kwargs.update(
                {
                    "nargs": "?",
                    "const": "true",
                    "choices": [True, False],
                },
            )
        if arg not in known_args:
            parser.add_argument(arg, **arg_kwargs)
        known_args.add(arg)
    d = parser.parse_args(args)
    logger.debug(f"dict parsed from cli args: {pformat_yaml(d)}")
    return dict_from_flat_dict(d.__dict__)
