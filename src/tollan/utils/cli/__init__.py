import argparse
import re

from ..fmt import pformat_yaml
from ..general import dict_from_flat_dict
from ..log import logger
from ..yaml import yaml_loads

__all__ = ["dict_from_cli_args"]


def dict_from_cli_args(args):
    """Return a nested dict composed from CLI arguments.

    This is useful to compose nested dict from flag. Nested keys can
    be specified using syntax like ``--a.b.c``. Nested lists are
    supported with the index as the key: ``--a.0.c``. The values
    of the options are parsed as YAML string.
    """

    logger.debug(f"parse command line args: {args}")

    parser = argparse.ArgumentParser()
    re_arg = re.compile(r"^--(?P<key>[a-zA-Z_]([a-zA-z0-9_.\[\]+])*)")
    n_args = len(args)
    for i, arg in enumerate(args):
        # collect all items that are argument keys.
        m = re_arg.match(arg)
        if m is None:
            continue
        if i + 1 < n_args:
            val = args[i + 1]
        else:
            # the last item
            val = None
        arg_kwargs = dict()
        if val is None or re_arg.match(val) is not None:
            # the next item is a validate arg, this is a flag
            arg_kwargs["action"] = "store_true"
        else:
            # parse the item with config yaml loader
            arg_kwargs["type"] = yaml_loads
        parser.add_argument(arg, **arg_kwargs)
    d = parser.parse_args(args)
    logger.debug(f"dict parsed from cli args: {pformat_yaml(d)}")
    return dict_from_flat_dict(d.__dict__)
