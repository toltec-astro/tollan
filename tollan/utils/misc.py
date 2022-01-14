import functools
import collections.abc
from types import ModuleType
import sys
import importlib
from contextlib import ContextDecorator
import itertools
from pathlib import Path, PurePath, WindowsPath
import urllib
import inspect
from collections import OrderedDict
from urllib.parse import urlsplit, urlunsplit
from typing import NamedTuple
import re
import subprocess
from io import TextIOWrapper
import os


_excluded_from_all = set(globals().keys())


def ensure_abspath(p):
    """Return the fully expanded path for `p`."""
    return Path(p).expanduser().resolve()


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


def module_from_path(filepath, name=None):
    """Load module from filepath."""
    filepath = Path(filepath)
    if name is None:
        name = f'_module_from_path_{filepath.stem}'
    spec = importlib.util.spec_from_file_location(
            name, filepath.as_posix())
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
    re_list_append_key = re.compile(r'<<\d?')
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
                k = int(k)
                if re.match(re_list_append_key, str(k)) is not None:
                    d.append(default)
                    k = -1
                dv = d[k]
            else:
                dv = d.setdefault(k, default)
            if not isinstance(
                    dv, (collections.abc.Mapping, collections.abc.Sequence)):
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


def dict_product(**kwargs):
    """
    Return the Cartesian product of dicts.
    """
    return (dict(zip(kwargs.keys(), x))
            for x in itertools.product(*kwargs.values()))


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

        def hooked(obj, *args, **kwargs):
            self.func_hooked(obj, *args, **kwargs)
            func(obj, *args, **kwargs)
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


class FileLoc(NamedTuple):
    """
    A simple structure to hold file location info.
    """

    uri: str
    netloc: str
    path: Path

    def exists(self):
        return self.is_local and self.path.exists()

    @property
    def is_local(self):
        return self.netloc == ''

    @property
    def is_remote(self):
        return not self.is_local

    def __repr__(self):
        return f'{self.__class__.__name__}({self.rsync_path})'

    @property
    def rsync_path(self):
        if self.is_local:
            return self.path.as_posix()
        return f'{self.netloc}:{self.path}'


def fileloc(loc, local_parent_path=None, remote_parent_path=None):
    """Return a `~tollan.utils.FileLoc` object.

    Parameters
    ----------

    loc : str, `~pathlib.Path`, tuple, `~tollan.utils.FileLoc`

        The location of the file, composed of the hostname and the path.
        It can take the form of the follows:

        * ``str``. In this case, `loc` is interpreted as a local path, or a
          remote path similar to sftp syntax: ``<hostname>:<abspath>``.
          A remote relative path is not supported.

        * `~pathlib.Path`. It is a local path.

        * Tuple of ``(<hostname>, <abspath>)``. It is a remote path, unless
          ``hostname`` is "localhost". A remote relative path is not
          supported.

        * `~tollan.utils.FileLoc`. It is returned unaltered.

    local_parent_path : str, `~pathlib.Path`, None

        If not None, this is used as the parent of local
        relative path. Otherwise, the current path (``pwd``) is used.
        Ignored if `loc` is `~tollan.utils.FileLoc`.

    remote_parent_path : str, `~pathlib.Path`, None

        If not None and is absolute, this is used as the parent of remote
        relative path. Otherwise, `ValueError` will be raised if a remote
        relative path is given.
        Ignored if `loc` is `~tollan.utils.FileLoc`.
    """
    if isinstance(loc, FileLoc):
        return loc

    def _get_abs_path(h, p):
        p = Path(p)
        if isinstance(p, WindowsPath):
            if h is None or h == '':
                # local window path
                return ensure_abspath(p)
            # remote window path
            raise ValueError('fileloc does not support remote windows path')
        if p.is_absolute():
            # TODO revisit this. may need to resolve anyways
            return p
        # relative path
        # local file
        if h is None or h == '':
            if local_parent_path is not None:
                return ensure_abspath(Path(
                        local_parent_path).joinpath(p))
            return ensure_abspath(p)
        # remote file
        if remote_parent_path is None or not Path(
                remote_parent_path).is_absolute():
            raise ValueError(
                    'remote path shall be absolute if '
                    'no remote_parent_path is set.')
        return Path(remote_parent_path).joinpath(p)

    if isinstance(loc, str):
        # https://stackoverflow.com/a/57463161/1824372
        if loc.startswith('file://'):
            uri_parsed = urllib.parse.urlparse(loc)
            uri = loc
            h = uri_parsed.netloc
            p = urllib.parse.unquote(uri_parsed.path)
            p = _get_abs_path(h, p)
        elif re.match(r'^[A-Z]:\\\w', loc):
            # local window path
            h = None
            p = _get_abs_path(h, loc)
            uri = p.as_uri()
        elif ':' in loc:
            h, p = loc.split(':', 1)
            p = _get_abs_path(h, p)
            uri = urlunsplit(
                    urlsplit(p.as_uri())._replace(netloc=h))
        else:
            # local file
            h = None
            p = _get_abs_path(h, loc)
            uri = p.as_uri()
    elif isinstance(loc, PurePath):
        # local file
        h = None
        p = _get_abs_path(h, loc)
        uri = p.as_uri()
    elif isinstance(loc, tuple):
        h, p = loc
        p = _get_abs_path(h, p)
        uri = urlunsplit(
                urlsplit(p.as_uri())._replace(netloc=h))
    else:
        raise ValueError(f'invalid file location {loc}.')
    if h is None or h == 'localhost' or h == '':
        h = ''
    return FileLoc(uri=uri, netloc=h, path=p)


def make_subprocess_env():
    # on mac os the dyld path may not get propagated
    env = {
            'DYLD_LIBRARY_PATH': os.environ.get('LIBRARY_PATH', None),
            'LD_LIBRARY_PATH': os.environ.get('LIBRARY_PATH', None),
            'PATH': os.environ.get('PATH', None)
            }
    return {k: v for k, v in env.items() if v is not None}


def call_subprocess_with_live_output(cmd, logger_func=None):
    """Execute `cmd` in subprocess with live output."""

    def _handle_ln(ln):
        # logger.debug(ln.decode().strip())
        # print(ln)
        sys.stderr.write(ln)
        if logger_func is not None:
            logger_func(ln.strip())

    with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=make_subprocess_env(),
            ) as proc:
        reader = TextIOWrapper(proc.stdout, newline='')
        for ln in iter(
                reader.readline, b''):
            _handle_ln(ln)
            if proc.poll() is not None:
                sys.stderr.write('\n')
                break
        retcode = proc.returncode
        if retcode:
            # get any remaining message
            ln, _ = proc.communicate()
            _handle_ln(ln.decode())
            _handle_ln(
                f"The process exited with error code: {retcode}\n")
            return False
        return True


def dict_from_regex_match(pattern, input_, type_dispatcher=None):
    """Return a dict from matching `pattern` to `input_`.

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
        type_dispatcher = dict()
    m = re.match(pattern, input_)
    if m is None:
        return None

    result = dict()

    for k, v in m.groupdict().items():
        if k in type_dispatcher:
            result[k] = type_dispatcher[k](v)
        else:
            result[k] = v
    return result


def getname(obj):
    """Return the name of `obj`.

    The inverse of `getobj`.
    """
    if inspect.isclass(obj):
        module = obj.__module__
        qualname = obj.__qualname__
        if module is None or module == str.__module__:
            return qualname
        return f"{module}.{qualname}"
    raise NotImplementedError(f"cannot get name for obj {obj}")


__all__ = list(set(globals().keys()).difference(_excluded_from_all))
