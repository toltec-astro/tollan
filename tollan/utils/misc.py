import functools
import collections.abc
from types import ModuleType
import sys
import importlib
from contextlib import ContextDecorator
import itertools
from pathlib import Path
import urllib
from collections import OrderedDict


_excluded_from_all = set(globals().keys())


def getobj(name, *args):
    """Return python object specified by `name`.

    `name` shall be of form ``a.b[:c[.d]]`` where ``a.b`` specifies
    the module and the optional ``:c.d`` specifies member attribute.

    """
    if not isinstance(name, str):
        raise ValueError("name must be a string.")
    sep = ':'
    if sep not in name:
        name = f"{name}:"
    module, attr = name.split(sep, 1)
    try:
        module = importlib.import_module(module)
    except Exception:
        if not args:
            raise
        return args[0]  # return the default if specified
    if attr == '':
        return module
    return rgetattr(module, attr)


def rreload(m: ModuleType):
    """Reload module recursively.

    Different from the `importlib.reload`, this also reloads submodules
    (modules with names prefixed by ``m.__name__``).

    """

    name = m.__name__  # get the name that is used in sys.modules
    name_ext = name + '.'  # support finding sub modules or packages

    def compare(loaded: str):
        return (loaded == name) or loaded.startswith(name_ext)

    # prevent changing iterable while iterating over it
    all_mods = tuple(sys.modules)
    sub_mods = filter(compare, all_mods)
    for pkg in sorted(
            sub_mods, key=lambda item: item.count('.'), reverse=True):
        importlib.reload(sys.modules[pkg])


def rgetattr(obj, attr, *args):
    """Get attribute recursively.

    Nested attribute is specified as `a.b`.

    """
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)
    return functools.reduce(_getattr, [obj] + attr.split('.'))


def rupdate(d, u):
    """Update dict recursively.

    This will update `d` with items in `u` in a recursive fashion.
    Keys in d will not be deleted if they are found in `u`.

    Parameters
    ----------
    d, u : dict


    Returns
    -------
    None
        Dict `d` is updated in place.

    Notes
    -----
    See [1]_.

    .. [1] https://stackoverflow.com/a/52099238/1824372

    """

    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        for k, v in u.items():
            if not isinstance(v, collections.abc.Mapping):
                # u[k] is not a dict, nothing to merge, so just set it,
                # regardless if d[k] *was* a dict
                d[k] = v
            else:
                # note: u[k] is a dict
                # get d[k], defaulting to a dict, if it doesn't previously
                # exist
                dv = d.setdefault(k, {})
                if not isinstance(dv, collections.abc.Mapping):
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
    return OrderedDict([
        (key(v) if callable(key) else v[key], v)
        for v in lst])


class hookit(ContextDecorator):
    """A context manager that allow inject code to object's method.

    Parameters
    ----------
    obj : object
        The object to alter.

    name : str
        The name of the method to hook.

    """

    def __init__(self, obj, name: str):
        self.obj = obj
        self.name = name
        self.func_hooked = getattr(obj, name)

    def set_post_func(self, func):
        """Call `func` after the hooked function.

        Parameters
        ----------
        func : callable
            The function to call after the hooked function.
        """

        def hooked(obj):
            self.func_hooked(obj)
            func(obj)
        setattr(self.obj, self.name, hooked)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        setattr(self.obj, self.name, self.func_hooked)


def patchit(obj, name, pass_patched=False):
    """Return a decorator that replace attribute with decorated
    item.

    Parameters
    ----------
    obj : object
        The object to alter.

    name : str
        The name of the attribute to replace.

    pass_patched : bool
        If set to True, the original attribute will be passed to as
        the first argument to the decorated function.

    """

    patched_attr_name = f'__patched_attr_{name}'
    if hasattr(obj, patched_attr_name):
        raise RuntimeError(f"attr {name} of obj {obj} is already patched")
    old_func = getattr(obj, name)

    def decorator(func):
        if pass_patched:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(old_func, *args, **kwargs)
            new_func = wrapper
        new_func = func
        setattr(obj, patched_attr_name, old_func)
        setattr(obj, name, new_func)
        return new_func
    return decorator


def mapreduce(map_func, reduce_func, gen, *args, **kwargs):
    """Return a map and reduce generator.

    Parameters
    ----------
    map_func : callable
        The map function.

    reduce_func : callable
        The reduce_function.

    gen : generator or iterator
        The inputs.

    *args, **kwargs
        Passed to the `functools.reduce` function.

    Returns
    -------
    generator
        The map-reduce generator.

    """
    return functools.reduce(reduce_func, map(map_func, gen), *args, **kwargs)


def anysum(a, b):
    """Return the sum of two objects."""
    try:
        return a + b
    except TypeError:
        return itertools.chain(a, b)


def mapsum(map_func, gen, *args, **kwargs):
    """Return a map and sum generator."""
    return mapreduce(map_func, anysum, gen, *args, **kwargs)


def ensure_prefix(s, p):
    """Return a new string with prefix `p` if it does not."""
    if s.startswith(p):
        return s
    return f"{p}{s}"


def to_typed(s):
    """Return a typed object from string `s` if possible."""
    if not isinstance(s, str):
        raise ValueError("input object has to be string.")
    if '.' not in s:
        try:
            return int(s)
        except ValueError:
            pass
    try:
        return float(s)
    except ValueError:
        return s


# https://stackoverflow.com/a/57463161/1824372
def file_uri_to_path(file_uri):
    """
    This function returns a pathlib.PurePath object for the supplied file URI.

    Parameters
    ----------
    file_uri : str
        The file URI.

    Returns
    -------
    Path
        The path the URI refers to.

    """
    file_uri_parsed = urllib.parse.urlparse(file_uri)
    if file_uri_parsed.scheme != 'file':
        raise ValueError(f"not a file uri: {file_uri}")
    file_uri_path_unquoted = urllib.parse.unquote(file_uri_parsed.path)
    result = Path(file_uri_path_unquoted)
    if not result.is_absolute():
        raise ValueError(
                f"invalid file uri {file_uri} : path {result} not absolute")
    return result


__all__ = list(set(globals().keys()).difference(_excluded_from_all))
