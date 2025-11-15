"""
General logging utilities.

Features:
- Global loguru logger instance (`logger`)
- Decorators/context managers for logging entry/exit (`logit`) and timing (`timeit`)
- Logger reset utility (`reset_logger`)

Examples
--------
>>> from tollan.utils.log import logger, logit, timeit
>>> @logit(logger.info, "Running task")
... def task():
...     pass
>>> @timeit
... def timed_task():
...     pass
"""

from __future__ import annotations

import contextlib
import functools
import sys
import time
from collections.abc import Callable
from contextlib import ContextDecorator
from typing import TYPE_CHECKING, Any, overload

from astropy.utils.console import human_time
from loguru import logger as _loguru_logger

if TYPE_CHECKING:
    from loguru import Logger

__all__ = [
    "logger",
    "logit",
    "reset_logger",
    "timeit",
]

logger = _loguru_logger
"""Global loguru logger instance."""


def _rebind_loguru_log_func(log_func: Callable, depth: int) -> Callable:
    """Return a loguru log function with adjusted stack depth.

    Ensures correct attribution in logs.
    """
    logger_inst = getattr(log_func, "__self__", None)
    if logger_inst is None:
        return log_func
    log_func_name = log_func.__name__  # ty: ignore[unresolved-attribute]
    return getattr(logger_inst.opt(depth=depth), log_func_name)


class logit(ContextDecorator):  # noqa: N801
    """
    Decorator/context manager to log entry and exit of a function or code block.

    Parameters
    ----------
    log_func : callable
        Logging function (e.g., logger.info)
    msg : str
        Message to log
    base_depth : int, optional
        Stack depth adjustment (default: 0)
    """

    def __init__(
        self,
        log_func: Callable,
        msg: str,
        base_depth: int = 0,
    ) -> None:
        self._log_func = log_func
        self._base_depth = base_depth
        self._msg = msg

    def _rebind(self, offset_depth: int) -> None:
        """Rebind log function with adjusted depth."""
        self._log_func = _rebind_loguru_log_func(
            self._log_func,
            self._base_depth + offset_depth,
        )

    def __enter__(self) -> None:
        """Log entry message."""
        self._rebind(offset_depth=1)
        self._log_func(f"{self._msg} ...")

    def __exit__(self, *args: object) -> None:
        """Log exit message."""
        self._log_func(f"{self._msg} done")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._rebind(offset_depth=2)
        return super().__call__(*args, **kwargs)


class logged_closing(contextlib.closing):  # noqa: N801
    """
    Context manager that logs closing of an object (like contextlib.closing).

    Parameters
    ----------
    log_func : callable
        Logging function
    thing : object
        Object with a .close() method
    msg : str, optional
        Custom log message (default: "close {thing}")
    """

    thing: Any

    def __init__(
        self,
        log_func: Callable,
        thing: Any,
        msg: str | None = None,
    ) -> None:
        super().__init__(thing)
        self._log_func = log_func
        if msg is None:
            msg = f"close {self.thing}"
        self._msg = msg

    def __exit__(self, *exc_info: object) -> None:
        """Close the thing with logging."""
        with logit(self._log_func, self._msg, base_depth=1):
            self.thing.close()


class timeit(ContextDecorator):  # noqa: N801
    """
    Decorator/context manager to log execution time of a function or code block.

    Uses astropy.utils.human_time for formatting.
    Can be used as a decorator or with 'with' statement.
    """

    _logger: Logger

    @overload
    def __new__(cls, arg: str, **kwargs) -> timeit: ...

    @overload
    def __new__[F: Callable](cls, arg: F) -> F: ...

    def __new__(cls, arg, **kwargs):
        """Return timeit instance."""
        if callable(arg):
            return cls(arg.__name__, **kwargs)(arg)
        return super().__new__(cls)

    def __init__(self, message: str, level: str = "DEBUG") -> None:
        self._message = message
        self._level = level
        self._logger = _loguru_logger.patch(
            lambda r: r.update(name=f"timeit: {r['name']}"),
        ).opt(depth=1)

    def __enter__(self) -> None:
        self._logger.log(self._level, f"{self._message} ...")
        self._start = time.time()

    def __exit__(self, *args: object) -> None:
        elapsed = time.time() - self._start
        self._logger.log(
            self._level,
            f"{self._message} done in {self._format_time(elapsed)}",
        )

    def __call__(self, func: Callable) -> Callable:
        """Decorate function to log its execution.

        Parameters
        ----------
        func : Callable
            Function to wrap with logging

        Returns
        -------
        Callable
            Wrapped function that logs execution
        """
        self._logger = self._make_logger_for_decorator(func)
        return super().__call__(func)

    @staticmethod
    def _format_time(time):
        max_ms = 15
        if time < max_ms:
            return f"{time * 1e3:.0f}ms"
        return f"{human_time(time).strip()}"

    @staticmethod
    @functools.cache
    def _make_logger_for_decorator(logger_ctx):
        name = logger_ctx.__module__
        fname = logger_ctx.__qualname__
        line = logger_ctx.__code__.co_firstlineno

        return _loguru_logger.patch(
            lambda r: r.update(
                name=f"timeit: {name}",
                function=fname,
                line=line,
            ),
        )


def reset_logger(
    sink: Any = sys.stderr,
    *,
    verbose: bool = True,
    level: str = "DEBUG",
    **kwargs: Any,
) -> None:
    """
    Reset the global logger to default configuration.

    Removes all handlers and adds a new one with the given options.
    """
    if verbose:
        logger.debug(f"reset logger with {sink=} {level=}")
    logger.remove()
    logger.add(sink, level=level, **kwargs)
