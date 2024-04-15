"""A submodule that contains a general utilities and helpers."""

from __future__ import annotations

import collections.abc
import contextlib
import functools
import importlib.util
import inspect
import itertools
import os
import re
import sys
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import scalpl
import wrapt
from astropy.utils.data import get_readable_fileobj

__all__ = [
    "ensure_abspath",
    "ensure_readable_fileobj",
    "getobj",
    "getname",
    "module_from_path",
    "rreload",
    "rgetattr",
    "rupdate",
    "odict_from_list",
    "dict_product",
    "dict_from_flat_dict",
    "dict_to_flat_dict",
    "fcompose",
    "ObjectProxy",
    "add_to_dict",
    "ignore_unexpected_kwargs",
    "slugify",
    "list_from_filtered",
    "list_not_none",
]


def ensure_abspath(p: str | Path) -> Path:
    """Return the fullUnion[Uni,[y e,]anded] path."""
    return Path(p).expanduser().resolve()


def ensure_readable_fileobj(arg, *args, **kwargs):
    """Return a readable object.

    This differs from the `astropy.utils.data.get_readable_fileobj` in that it
    is no-op if `arg` is already readable.
    """
    if isinstance(arg, str | os.PathLike) and not os.path.isdir(arg):  # noqa: PTH112
        return get_readable_fileobj(arg, *args, **kwargs)
    if hasattr(arg, "read"):
        return contextlib.nullcontext(arg)
    raise ValueError(f"cannot create readable context for {arg}")


def getobj(name, *args):
    """Return python object specified by `name`.

    `name` shall be of form ``a.b[:c[.d]]`` where ``a.b`` specifies
    the module and the optional ``:c.d`` specifies member attribute.

    """
    if not isinstance(name, str):
        raise TypeError("name must be a string.")
    sep = ":"
    if sep not in name:
        name = f"{name}:"
    module, attr = name.split(sep, 1)
    try:
        module = importlib.import_module(module)
    except Exception:  # noqa: BLE001
        if not args:
            raise
        return args[0]  # return the default if specified
    if not attr:
        return module
    return rgetattr(module, attr)


def getname(obj, sep=":"):
    """Return specifier name of python object.

    This is the opposite of `getobj`.
    """
    if not hasattr(obj, "__qualname__"):
        raise TypeError("invalid object type.")
    module = obj.__module__
    name = obj.__qualname__
    if module is None or module == str.__class__.__module__:
        module = ""
    return f"{module}{sep}{name}"


def module_from_path(filepath, name=None):
    """Load module from filepath."""
    filepath = Path(filepath)
    if name is None:
        name = f"_module_from_path_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(name, filepath.as_posix())
    module = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(module)  # type: ignore
    return module


def rreload(m):
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


MT = collections.abc.Mapping
ST = collections.abc.Sequence


def rupdate(d, u, copy_subdict=True):  # noqa: C901
    r"""Update dict recursively.

    This will update `d` with items in `u` in a recursive fashion.

    `d` can be either list or dict. `u` has to be dict where int
    keys can be used to identify list items.

    When updating list, the special key matches ``+(\d+(:\d+)?)?`` can be used to
    extend list to the list.

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
    re_list_dsl = re.compile(r"^\+(?P<start>\d+)?(?:(?P<is_slice>:)(?P<end>\d+)?)?$")
    stack = [(d, u)]

    def _handle_list_dsl(d, k, default):
        m = re.match(re_list_dsl, str(k))
        if m is not None:
            md = m.groupdict()
            start = md.get("start", None)
            start = int(start) if start is not None else None
            end = md.get("end", None)
            end = int(end) if end is not None else None
            is_slice = md.get("is_slice", None)
            if start is None and is_slice is None:
                # by design end should be none
                assert end is None
                # this is just <<
                # extend to the end
                d.append(default)
                k = slice(-1, None)
            elif is_slice is None:
                # this is <<1 without the end specified
                # this is to insert a list between start and start+1
                k = slice(start, start)
            else:
                # this is full slice syntax 1:3, replaces the
                # sliced list with new list
                k = slice(start, end)
            # the slice is returned to handle list extend.
            return k, default
        try:
            k = int(k)
        except ValueError as e:
            raise ValueError(f"invalid key {k} for list update.") from e
        dv = d[k]
        return k, dv

    while stack:
        # here d can only be list or dict
        d, u = stack.pop(0)
        for k, v in u.items():
            # print(f"processing {d=} {u=} {k=} {v=}")
            if copy_subdict:  # noqa: SIM108
                default = {}  # subdicts in u will get copied to this
            else:
                default = None  # subdicts in u will be assigned to it.
            if isinstance(d, MT):
                # handle d as dict
                dv = d.setdefault(k, default)
            elif isinstance(d, ST):
                # list
                # dv here can be a slice object or a leaf value
                k, dv = _handle_list_dsl(d, k, default)  # noqa: PLW2901
                if isinstance(k, slice):
                    # handle slice extend syntax
                    if not isinstance(v, ST):
                        # wrap as a sequence
                        v = [v]  # noqa: PLW2901
                    # now u[k] is a list, and d[k] is a slice
                    # do the extending. there is no merging allowed here.
                    # TODO: dict in v is not copied in this case.
                    # print(f"{d=} {k=} {v=} {dv=}")
                    d[k] = v
                    continue
            # now k is a proper index to d, and dv is d[k]
            if not isinstance(v, MT):
                # u[k] is not a dict, nothing to merge, so just set it,
                # regardless if d[k] *was* a dict
                d[k] = v
                continue
            # now v = u[k] is dict
            if not isinstance(dv, MT | ST):
                # d[k] is not a container, so just set it to u[k],
                # overriding whatever it was
                d[k] = v  # type: ignore
            else:
                # both d[k] and u[k] are containers, push them on the stack
                # to merge further
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
    """Return the Cartesian product of dicts."""
    return (
        dict(zip(kwargs.keys(), x, strict=False))
        for x in itertools.product(*kwargs.values())
    )


def dict_from_flat_dict(dct):
    """Return dict from dict with flattened keys."""
    d = scalpl.Cut({})
    _missing = object()
    for k, v in dct.items():
        v0 = d.get(k, _missing)
        if v0 is _missing:
            d.setdefault(k, v)
            continue
        # update v to v0 if dict
        if isinstance(v0, dict):
            rupdate(v0, v)
        else:
            d[k] = v
    return d.data


def dict_to_flat_dict(dct, key_prefix="", list_index_as_key=False):  # noqa: C901
    """Return dict from dict with nested dicts."""

    def _dk(key):
        return f".{key}"

    def _lk(i):
        if list_index_as_key:
            return _dk(i)
        return f"[{i}]"

    def _nested_kvs(data) -> list | tuple:
        if isinstance(data, list | dict):
            kvs = []
            if isinstance(data, list):
                items = ((_lk(i), data[i]) for i in range(len(data)))
            else:
                items = ((_dk(key), data[key]) for key in data)
            for key, value in items:
                result = _nested_kvs(value)
                if isinstance(result, list):
                    if isinstance(value, dict | list):
                        kvs.extend([(f"{key}{item}", val) for (item, val) in result])
                elif isinstance(result, tuple):
                    kvs.append((f"{key}", result[1]))
                else:
                    pass
            return kvs
        # leaf
        return (None, data)

    if not isinstance(dct, dict):
        raise TypeError("only dict is allowed as input.")
    kvs = _nested_kvs(dct)
    # build the dict
    result = {}
    for k, v in kvs:
        _k = key_prefix + k.lstrip(".")
        result[_k] = v
    return result


def fcompose(*fs):
    """Return composition of functions."""

    def compose2(f, g):
        return lambda *a, **kw: f(g(*a, **kw))

    return functools.reduce(compose2, fs)


class ObjectProxy(wrapt.ObjectProxy):
    """A class to hold object for deferred initialization.

    Parameters
    ----------
    factory : callable, optional
        The facory fuction to invoke when :meth:`init` is called. The return
        value is set as the underlying instance of this proxy object.
        If None, the first argument of the call is used as the underlying instance.
    """

    def __init__(self, factory=None):
        self._self_factory = factory
        super().__init__(None)

    def proxy_init(self, *args, **kwargs):
        """Initialize this proxy."""
        if self._self_factory is None:
            if kwargs or len(args) > 1:
                raise ValueError("too many arguments.")
            if len(args) == 0:
                raise ValueError("too few arguments.")
            self.__wrapped__ = args[0]
            return self
        self.__wrapped__ = self._self_factory(*args, **kwargs)  # type: ignore
        return self

    def proxy_reset(self):
        """Reset this proxy."""
        self.__wrapped__ = None
        return self

    def proxy_initialized(self):
        """Return True if proxy is initialized."""
        return self.__wrapped__ is not None


def add_to_dict(d, key, exist_ok=True):
    """Return a decorator to add decorated item to dict.

    When key is callable, it generate the actual key by
    invoking it with the decorated item.
    """

    def decorator(thing):
        _key = key(thing) if callable(key) else key
        if not exist_ok and _key in d:
            raise ValueError("key={_key} exist.")
        d[_key] = thing
        return thing

    return decorator


def dict_from_regex_match(pattern, string, type_dispatcher=None):
    """Return a dict from matching `pattern` to `string`.

    If match failed, returns None.

    Parameters
    ----------
    pattern : str, `re.Pattern`
        The regex that matches to the `input_`.

    input_ : str
        The string to be matched.

    type_dispatcher : dict
        This specifies how the matched group values are handled after being
        extracted.
    """
    if type_dispatcher is None:
        type_dispatcher = {}
    m = re.match(pattern, string)
    if m is None:
        return None

    result = {}
    for k, v in m.groupdict().items():
        if k in type_dispatcher:
            result[k] = type_dispatcher[k](v)
        else:
            result[k] = v
    return result


def ignore_unexpected_kwargs(func: Callable[..., Any]) -> Callable[..., Any]:
    """Return a decorated function to allow passing extra kwargs."""
    # https://stackoverflow.com/a/63685135

    def filter_kwargs(kwargs: dict) -> dict:
        sig = inspect.signature(func)
        # Parameter.VAR_KEYWORD - a dict of keyword arguments that aren't bound
        # to any other
        if any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            # if **kwargs exist, return directly
            return kwargs

        def _f(p):
            return p.kind in {
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }

        _params = filter(_f, sig.parameters.values())
        return {p.name: kwargs[p.name] for p in _params if p.name in kwargs}

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        kwargs = filter_kwargs(kwargs)
        return func(*args, **kwargs)

    return wrapper


def slugify(value):
    """Convert string to a short form."""
    # https://github.com/django/django/blob/master/django/utils/text.py
    value = str(value)
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def list_from_filtered(flt, gen):
    """Return a list from filtering the iterable."""
    return list(filter(flt, gen))


def list_not_none(gen):
    """Return a list containing only not None."""
    return list(filter(lambda item: item is not None, gen))
