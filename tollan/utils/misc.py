import functools
import collections
from types import ModuleType
import sys
import importlib
from contextlib import ContextDecorator
import os


def touch_file(out_file):
    """Same as the shell command `touch`."""

    with open(out_file, 'a'):
        os.utime(out_file, None)


def getobj(name, default=None):
    """Return python object specified by `name`.

    `name` is specified as `a.b::c`.

    """
    try:
        module, func = name.split("::")
        module = importlib.import_module(module)
    except Exception:
        pass
    else:
        return getattr(module, func)
    return default


def getdict(obj, keys=None):
    """Return a dict composed from object's attributes.

    `keys` is used to specify what attributes to include in the created dict.
    If `keys` is None, the `__all__` list is used if present, otherwise use all
    attributes that does not starts with ``_``. If `keys` is callable, it is
    called with `obj` to get a list of keys.

    Parameters
    ----------
    keys: list, callable, or None
        Specify the attributes to include.

    Returns
    -------
    dict:
        A dict contains selected object's attribute names and values.

    """
    if keys is None:
        if hasattr(obj, '__all__'):
            keys = obj.__all__
        else:
            keys = filter(lambda k: not k.startswith('_'), dir(obj))
    else:
        if callable(keys):
            keys = keys(obj)

    return {k: getattr(obj, k) for k in keys}


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
    d, u: dict


    Returns
    -------
    None
        Dict `d` is updated in place.

    .. [1] https://stackoverflow.com/a/52099238/1824372

    """

    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        for k, v in u.items():
            if not isinstance(v, collections.Mapping):
                # u[k] is not a dict, nothing to merge, so just set it,
                # regardless if d[k] *was* a dict
                d[k] = v
            else:
                # note: u[k] is a dict
                # get d[k], defaulting to a dict, if it doesn't previously
                # exist
                dv = d.setdefault(k, {})
                if not isinstance(dv, collections.Mapping):
                    # d[k] is not a dict, so just set it to u[k],
                    # overriding whatever it was
                    d[k] = v
                else:
                    # both d[k] and u[k] are dicts, push them on the stack
                    # to merge
                    stack.append((dv, v))


class hookit(ContextDecorator):
    """A context manager that allow inject code to object's method.

    Parameters
    ----------
    obj: object
        The object to alter.

    name: str
        The name of the method to hook.

    """

    def __init__(self, obj, name: str):
        self.obj = obj
        self.name = name
        self.func_hooked = getattr(obj, name)

    def set_post_func(self, func):
        """Call `func` after the hooked function."""

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
    obj: object
        The object to alter.

    name: str
        The name of the attribute to replace.

    pass_patched: bool
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
