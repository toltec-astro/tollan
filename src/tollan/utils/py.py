"""Python utility classes and functions."""

from __future__ import annotations

import functools
import importlib.util
import sys
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

    def __init__(self, factory: None | Callable[..., T] = None) -> None:
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
    """Return a Python object by dotted path (e.g. 'module:attr.subattr')."""
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
    """Return the specifier name of a Python object (opposite of getobj)."""
    if not hasattr(obj, "__qualname__"):
        msg = "invalid object type."
        raise TypeError(msg)
    module = obj.__module__
    name = obj.__qualname__
    if module is None or module == str.__class__.__module__:
        module = ""
    return f"{module}{sep}{name}"


def module_from_path(filepath: str | Path, name: None | str = None) -> object:
    """Load a Python module from a file path."""
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
    """Recursively reload a module and all its submodules."""
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
    """Recursively get a nested attribute (e.g. 'a.b.c')."""

    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return functools.reduce(_getattr, [obj, *attr.split(".")])
