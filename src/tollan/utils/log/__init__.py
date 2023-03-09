#!/usr/bin/env python


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

    def __init__(self, log_func, msg):
        self.log_func = log_func
        self.msg = msg

    def __enter__(self):
        self.log_func(f"{self.msg} ...")

    def __exit__(self, *args):
        self.log_func(f"{self.msg} done")
