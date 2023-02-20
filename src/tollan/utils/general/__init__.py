#!/usr/bin/env python


import collections.abc
import contextlib
import functools
import importlib
import itertools
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from types import ModuleType
from typing import Union

from astropy.utils.data import get_readable_fileobj


def ensure_abspath(p: Union[str, Path]) -> Path:
    """Return the fully expanded path."""
    return Path(p).expanduser().resolve()


def ensure_readable_fileobj(arg, *args, **kwargs):
    """Return a readable object."""
    ctx = None
    if isinstance(arg, (str, os.PathLike)) and not os.path.isdir(arg):
        ctx = get_readable_fileobj(arg, *args, **kwargs)
        return ctx
    if hasattr(arg, "read"):
        return contextlib.nullcontext(arg)
    raise ValueError(f"cannot create readable context for {arg}")


def getobj(name, *args):
    """Return python object specified by `name`.

    `name` shall be of form ``a.b[:c[.d]]`` where ``a.b`` specifies
    the module and the optional ``:c.d`` specifies member attribute.

    """
    if not isinstance(name, str):
        raise ValueError("name must be a string.")
    sep = ":"
    if sep not in name:
        name = f"{name}:"
    module, attr = name.split(sep, 1)
    try:
        module = importlib.import_module(module)
    except Exception:
        if not args:
            raise
        return args[0]  # return the default if specified
    if attr == "":
        return module
    return rgetattr(module, attr)


def module_from_path(filepath, name=None):
    """Load module from filepath."""
    filepath = Path(filepath)
    if name is None:
        name = f"_module_from_path_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(name, filepath.as_posix())
    # print(filepath)
    # print(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rreload(m: ModuleType):
    """Reload module recursively.

    Different from the `importlib.reload`, this also reloads submodules
    (modules with names prefixed by ``m.__name__``).

    """

    name = m.__name__  # get the name that is used in sys.modules
    name_ext = name + "."  # support finding sub modules or packages

    def compare(loaded: str):
        return (loaded == name) or loaded.startswith(name_ext)

    # prevent changing iterable while iterating over it
    all_mods = tuple(sys.modules)
    sub_mods = filter(compare, all_mods)
    for pkg in sorted(sub_mods, key=lambda item: item.count("."), reverse=True):
        importlib.reload(sys.modules[pkg])


def rgetattr(obj, attr, *args):
    """Get attribute recursively.

    Nested attribute is specified as `a.b`.

    """

    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return functools.reduce(_getattr, [obj] + attr.split("."))


def rupdate(d, u, copy_subdict=True):
    """Update dict recursively.

    This will update `d` with items in `u` in a recursive fashion.

    `d` can be either list or dict. `u` has to be dict where int
    keys can be used to identify list items.

    When updating list, the special key matches ``<<\\d+`` can be used to
    append item to the list.

    Parameters
    ----------
    d : dict, list
        The container to be updated

    u : dict
        The update dict.

    copy_subdict : bool
        If True, subdicts in `u` will get copied to `d`, such that
        further change in `d` will not propagate back to `u`.

    update_list : bool
        If True, value with int key will be used to update list.

    Returns
    -------
    None
        Dict `d` is updated in place.

    Notes
    -----
    See [1]_.

    .. [1] https://stackoverflow.com/a/52099238/1824372

    """
    re_list_append_key = re.compile(r"<<(:P<index>\d+)?")
    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        for k, v in u.items():
            # print(f"processing {d=} {u=} {k=} {v=}")
            if not isinstance(v, collections.abc.Mapping):
                # u[k] is not a dict, nothing to merge, so just set it,
                # regardless if d[k] *was* a dict
                d[k] = v
                continue
            # now v = u[k] is dict
            # d may be list or dict. For list, we check the special key
            # "<<" to append a new item.
            if copy_subdict:
                default = dict()  # subdicts in u will get copied to this
            else:
                default = None  # subdicts in u will be assigned to it.
            if isinstance(d, collections.abc.Sequence):
                m = re.match(re_list_append_key, str(k))
                if m is not None:
                    k = int(m.groupdict().get("index", len(d)))
                    d.insert(k, default)
                else:
                    k = int(k)
                dv = d[k]
            else:
                dv = d.setdefault(k, default)
            if not isinstance(dv, (collections.abc.Mapping, collections.abc.Sequence)):
                # d[k] is not a dict, so just set it to u[k],
                # overriding whatever it was
                d[k] = v
            else:
                # both d[k] and u[k] are dicts, push them on the stack
                # to merge
                stack.append((dv, v))


def odict_from_list(lst, key):
    """Return an ordered dict from list.

    Parameters
    ----------
    key : str or callable
        The key to use. If str, the items in list shall be dict that
        contains key `key`. If callable, it shall return the key
        when called with each item.

    Returns
    -------
    OrderedDict
        The ordered dict constructed from the list.
    """
    return OrderedDict([(key(v) if callable(key) else v[key], v) for v in lst])


def dict_product(**kwargs):
    """
    Return the Cartesian product of dicts.
    """
    return (dict(zip(kwargs.keys(), x)) for x in itertools.product(*kwargs.values()))


def compose(*fs):
    """Return composition of functions."""

    def compose2(f, g):
        return lambda *a, **kw: f(g(*a, **kw))

    return functools.reduce(compose2, fs)
