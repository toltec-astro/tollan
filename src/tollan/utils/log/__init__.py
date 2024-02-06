"""A submodule of logging related utilties."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager, ContextDecorator

from astropy.utils.console import human_time
from loguru import logger as _loguru_logger

__all__ = ["logger", "logit"]


logger = _loguru_logger
"""A global logger instance."""


def _rebind_loguru_log_func(log_func, depth):
    """Return the log function with depth adjusted."""
    # this is to return the logger with proper depth
    logger = getattr(log_func, "__self__", None)
    if logger is None:
        return log_func
    log_func_name = log_func.__name__
    # this is hacky but works
    # depth = min(2, len(inspect.stack()) - 2)
    return getattr(logger.opt(depth=depth), log_func_name)


class logit(ContextDecorator):  # noqa: N801
    """Decorator that logs the execution of the decorated item.

    Parameters
    ----------
    log_func: callable
        The logging function to use.

    msg: str
        The message body to use.
    """

    def _rebind(self, offset_depth):
        self._log_func = _rebind_loguru_log_func(
            self._log_func,
            self._base_depth + offset_depth,
        )

    def __init__(self, log_func, msg, base_depth=0):
        self._log_func = log_func
        self._base_depth = base_depth
        self.msg = msg
        self._rebind(offset_depth=1)

    def __enter__(self):
        self._log_func(f"{self.msg} ...")

    def __exit__(self, *args):
        self._log_func(f"{self.msg} done")

    def __call__(self, *args, **kwargs):  # noqa: D102
        self._rebind(offset_depth=2)
        return super().__call__(*args, **kwargs)


class logged_closing(AbstractContextManager):  # noqa: N801
    """A slightly modified version of `contextlib.closing` with logging."""

    def __init__(self, log_func, thing, msg=None):
        self._log_func = log_func
        self.thing = thing

        if msg is None:
            msg = f"close {self.thing}"
        self._msg = msg

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):
        with logit(self._log_func, self._msg, base_depth=1):
            self.thing.close()


class timeit(ContextDecorator):  # noqa: N801
    """Context decorator that logs the execution time of the decorated item.

    Parameters
    ----------
    arg: object or str
        If `arg` type is `str`, a new decorator is returned which uses `arg`
        in the generated message in places of the name of the decorated object.
    """

    _logger = _loguru_logger.patch(
        lambda r: r.update(name=f'timeit: {r["name"]}'),
    )

    def __new__(cls, arg, **kwargs):  # noqa: D102
        if callable(arg):
            return cls(arg.__name__, **kwargs)(arg)
        return super().__new__(cls)

    def __init__(self, msg, level="DEBUG"):
        self.msg = msg
        self._level = level
        self._logger = self._logger.opt(depth=1)

    def __enter__(self):
        self._logger.log(self._level, f"{self.msg} ...")
        self._start = time.time()

    def __exit__(self, *args):
        elapsed = time.time() - self._start
        self._logger.log(
            self._level,
            f"{self.msg} done in {self._format_time(elapsed)}",
        )

    def __call__(self, *args, **kwargs):  # noqa: D102
        self._logger = self._logger.opt(depth=2)
        return super().__call__(*args, **kwargs)

    @staticmethod
    def _format_time(time):
        max_ms = 15
        if time < max_ms:
            return f"{time * 1e3:.0f}ms"
        return f"{human_time(time).strip()}"
