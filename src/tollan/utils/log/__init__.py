#!/usr/bin/env python


import sys
from contextlib import ContextDecorator

from loguru import logger as _loguru_logger

__all__ = ["logger", "logit"]


logger = _loguru_logger
"""A global logger instance."""


class logit(ContextDecorator):
    """Decorator that logs the execution of the decorated item.

    Parameters
    ----------
    log_func: callable
        The logging function to use.

    msg: str
        The message body to use.
    """

    @staticmethod
    def _rebind_loguru_log_func(log_func):
        # hack to force loguru report the module name of caller frame
        logger = getattr(log_func, "__self__", None)
        if logger is None:
            return log_func
        log_func_name = log_func.__name__

        def _get_caller_info(frame):
            return {
                "name": frame.f_globals["__name__"],
                "function": frame.f_code.co_name,
                "line": frame.f_lineno,
            }

        frame = sys._getframe(2)
        logger = logger.patch(lambda record: record.update(**_get_caller_info(frame)))
        return getattr(logger, log_func_name)

    def __init__(self, log_func, msg):
        self.log_func = self._rebind_loguru_log_func(log_func)
        self.msg = msg

    def __enter__(self):
        self.log_func(f"{self.msg} ...")

    def __exit__(self, *args):
        self.log_func(f"{self.msg} done")
