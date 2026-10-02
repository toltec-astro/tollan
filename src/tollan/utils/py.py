"""Python utility classes and functions."""

from __future__ import annotations

import functools
import importlib.util
import sys
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Self

import wrapt

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

__all__ = [
    "ObjectProxy",
    "getname",
    "getobj",
    "module_from_path",
    "rgetattr",
    "rreload",
]


class ObjectProxy[T](wrapt.ObjectProxy):
    """
    Proxy object for deferred initialization.

    Use .proxy_init(...) to initialize, .proxy_reset() to clear,
    and .proxy_initialized() to check state.
    """

    def __init__(self, factory: Callable[..., T] | None = None) -> None:
        self._self_factory = factory
        super().__init__(None)

    def proxy_init(self, *args: object, **kwargs: object) -> Self:
        """Initialize this proxy with the factory or a direct value.

        Returns
        -------
        Self
            This proxy instance (for method chaining)
        """
        if self._self_factory is None:
            if kwargs or len(args) > 1:
                msg = "too many arguments."
                raise ValueError(msg)
            if len(args) == 0:
                msg = "too few arguments."
                raise ValueError(msg)
            self.__wrapped__ = args[0]
            return self
        self.__wrapped__ = self._self_factory(*args, **kwargs)
        return self

    def proxy_reset(self) -> Self:
        """Reset this proxy to uninitialized state.

        Returns
        -------
        Self
            This proxy instance (for method chaining)
        """
        self.__wrapped__ = None
        return self

    def proxy_initialized(self) -> bool:
        """Return True if proxy is initialized.

        Returns
        -------
        bool
            True if wrapped object is set, False otherwise
        """
        return self.__wrapped__ is not None


def getobj(name: str, *args: object) -> object:
    """Import a module or look up an object within it.

    Parameters
    ----------
    name : str
        Importable module name, optionally followed by ``:attr.subattr``.
    *args : object
        Optional positional fallback returned when importing the module raises
        an exception. Missing attributes after a successful import still raise.

    Returns
    -------
    object
        Imported module, selected attribute, or supplied fallback.

    Raises
    ------
    TypeError
        The name is not a string.
    AttributeError
        An attribute is missing from an imported module or nested object.
    """
    if not isinstance(name, str):
        msg = "name must be a string."
        raise TypeError(msg)
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
    if not attr:
        return module
    return rgetattr(module, attr)


def getname(obj: object, sep: str = ":") -> str:
    """Return an object's module and qualified name.

    Parameters
    ----------
    obj : object
        Object exposing ``__module__`` and ``__qualname__``.
    sep : str, optional
        Separator between module and qualified name, by default ``":"``.

    Returns
    -------
    str
        Object specifier. Builtins omit the module prefix; local objects may
        contain ``<locals>``. These forms are not importable by ``getobj()``.

    Raises
    ------
    TypeError
        The object does not have a qualified name.
    """
    if not hasattr(obj, "__qualname__"):
        msg = "invalid object type."
        raise TypeError(msg)
    module = obj.__module__
    name = obj.__qualname__
    if module is None or module == str.__class__.__module__:
        module = ""
    return f"{module}{sep}{name}"


def module_from_path(filepath: str | Path, name: str | None = None) -> ModuleType:
    """Load and execute a Python module from a file path.

    Parameters
    ----------
    filepath : str or pathlib.Path
        Python source file to execute.
    name : str, optional
        Module name; defaults to ``_module_from_path_`` plus the filename stem.

    Returns
    -------
    types.ModuleType
        Executed module. It is not registered in ``sys.modules``.

    Raises
    ------
    ImportError
        The path has no usable import specification or loader.
    """
    filepath = Path(filepath)
    if name is None:
        name = f"_module_from_path_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(name, filepath.as_posix())
    if spec is None:
        msg = f"cannot load module from path {filepath}: no spec found"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        msg = f"cannot load module from path {filepath}: no loader found"
        raise ImportError(msg)
    spec.loader.exec_module(module)
    return module


def rreload(m: ModuleType) -> None:
    """Reload a module and its already imported submodules.

    Parameters
    ----------
    m : types.ModuleType
        Module whose entries in ``sys.modules`` are reloaded, deepest first.
        Existing references held elsewhere are not replaced. Import errors
        propagate after any preceding reloads have already taken effect.
    """
    name = m.__name__  # get the name that is used in sys.modules
    name_ext = name + "."  # support finding sub modules or packages

    def compare(loaded: str) -> bool:
        return (loaded == name) or loaded.startswith(name_ext)

    # prevent changing iterable while iterating over it
    all_mods = tuple(sys.modules)
    sub_mods = filter(compare, all_mods)
    for pkg in sorted(sub_mods, key=lambda item: item.count("."), reverse=True):
        importlib.reload(sys.modules[pkg])


def rgetattr(obj: object, attr: str, *args: object) -> object:
    """Read a dotted attribute path, such as ``address.city``.

    An optional positional default is passed to ``getattr`` at each path
    segment. Traversal continues through that default when an intermediate
    attribute is absent. Present values, including None, are returned unchanged.
    Without a default, missing attributes raise AttributeError.

    Parameters
    ----------
    obj : object
        Starting object for attribute traversal.
    attr : str
        Dot-separated attribute names.
    *args : object
        At most one positional default for missing attributes.

    Returns
    -------
    object
        Value found after traversing every path segment.

    Raises
    ------
    AttributeError
        An attribute is absent and no default was supplied.
    """
    getter, parts = _rgetattr_path(attr)
    if not args:
        return getter(obj)
    for part in parts:
        obj = getattr(obj, part, *args)
    return obj


@functools.lru_cache(maxsize=256)
def _rgetattr_path(attr: str) -> tuple[attrgetter, tuple[str, ...]]:
    """Prepare a path without retaining source objects, defaults, or values."""
    return attrgetter(attr), tuple(attr.split("."))
