"""A subpackage that provides CLI utilities."""

import argparse
import re
from typing import Any

from .dict import dict_from_flat_dict
from .fmt import pformat_yaml
from .log import logger
from .yaml import yaml_loads

__all__ = ["dict_from_cli_args", "split_cli_args"]

_re_arg = re.compile(r"^--(?P<key>[a-zA-Z_](?:\.\[[\d:+\-]*\]|[\w.])*)")


def split_cli_args(re_name: str, args: list[str]) -> tuple[list[str], list[str]]:
    """Split the args based on regex match of the arg name.

    Parameters
    ----------
    re_name : str
        Regex pattern to match argument names
    args : list
        CLI arguments to split

    Returns
    -------
    tuple[list, list]
        Tuple of (matched args, unmatched args)
    """
    matched = []
    unmatched = []
    positional_key = "--"
    re_name_pattern = re.compile(re_name)
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
        m = _re_arg.match(arg)  # Use match() not fullmatch() to handle --key=value
        if m is None:
            if arg_pending_value:
                store.append(arg)
            else:
                # free floating value is always unmatched
                unmatched.append(arg)
            arg_pending_value = False
            continue
        mn = re_name_pattern.fullmatch(m.groupdict()["key"])
        store = unmatched if mn is None else matched
        store.append(arg)
        # Only expect separate value if no inline value (no =)
        arg_pending_value = "=" not in arg
    return matched, unmatched


def dict_from_cli_args(args: list[str]) -> dict:
    """Return a nested dict from CLI arguments.

    Uses rupdate to merge dotted keys, automatically handling conflicts
    and ListDSL patterns.

    Nested keys use dot notation: ``--a.b.c``. List DSL patterns use rupdate
    format: ``--items.[0]``, ``--items.[:0]``, ``--items.[]``.

    Parameters
    ----------
    args : list[str]
        CLI arguments to parse

    Returns
    -------
    dict
        Nested dictionary parsed from CLI arguments
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
        # Extract just the option name (--key) without any =value part
        arg_name = m.group(0)
        # Extract the key without -- prefix to use as dest (preserves [-1] etc.)
        key_name = m.groupdict()["key"]
        val = args[i + 1] if i + 1 < n_args else None
        # Check if this arg uses --key=value format
        has_inline_value = "=" in arg
        # parse the item with config yaml loader
        arg_kwargs: dict[str, Any] = {
            "type": yaml_loads,
            "required": True,
            "dest": key_name,  # Use original key to preserve [-1] etc.
        }
        # It's a flag if: no inline value AND (no next value OR next is another flag)
        if not has_inline_value and (val is None or _re_arg.match(val) is not None):
            # the next item is a validate arg, this is a flag
            # inorder to allow overriting flag, we make this
            # a boolean switch with default = True nargs=?
            arg_kwargs.update(
                {
                    "nargs": "?",
                    "const": "true",
                    "choices": [True, False],
                },
            )
        if arg_name not in known_args:
            parser.add_argument(arg_name, **arg_kwargs)
        known_args.add(arg_name)
    namespace = parser.parse_args(args)
    flat_dict = namespace.__dict__
    logger.debug(f"dict parsed from cli args: {pformat_yaml(flat_dict)}")

    # Handle empty flat_dict case
    if not flat_dict:
        return {}

    # Convert flat dict to nested dict using rupdate
    return dict_from_flat_dict(flat_dict)
