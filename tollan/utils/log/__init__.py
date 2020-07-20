#! /usr/bin/env python

from contextlib import ContextDecorator
import logging
import logging.config
import inspect
import time
import copy
from contextlib import contextmanager
from astropy.utils.console import human_time
from ..misc import rupdate
from . import console_color


__all__ = ['init_log', 'get_logger', 'timeit', 'logit']


presets = {

    'default': {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s:'
                          ' %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
                },
            'short': {
                'format': '[%(levelname)s] %(name)s: %(message)s'
                },
            },
        'handlers': {
            'default': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'short',
                },
            },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': 'DEBUG',
                'propagate': False
                },
            'matplotlib': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
                },
            'numexpr': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
                },
            'root': {
                'handlers': ['default'],
                'level': 'ERROR',
                'propagate': False
                },
            }
        },
    }


def init_log(
        preset='default',
        level='INFO',
        file_=None,
        colored=True,
        **kwargs):
    """Initialize logging with some sensible presets.

    Parameters
    ----------
    level: str
        The log level to use.

    file_: str, optional
        If set, the log are saved in `file_`.

    colored: bool
        If set to True, console messages will be colored.

    **kwargs:
        Update the preset with entries in this dict.

    """
    config = copy.deepcopy(presets[preset])
    rupdate(config, {'loggers': {'': {'level': level}}})
    if file_ is not None:
        rupdate(config, {
            'handlers': {'logfile': {
                    'class': 'logging.FileHandler',
                    'formatter': "standard",
                    'filename': file_
                    },
                },
            'loggers': {'': {'handlers': ['logfile', ]}},
            })
    if colored:
        rupdate(config, console_color.config)
    rupdate(config, kwargs)
    logging.config.dictConfig(config)


def get_logger(name=None):
    """Return a logger named `name` if specified, otherwise use the name
    of the calling context.
    """
    if name is None:
        name = inspect.stack()[1][3]
        # code = inspect.currentframe().f_back.f_code
        # func = [obj for obj in gc.get_referrers(code)][0]
        # name = func.__qualname__
    return logging.getLogger(name)


def _format_time(time):
    if time < 15:
        return f"{time * 1e3:.0f}ms"
    else:
        return f"{human_time(time).strip()}"


class timeit(ContextDecorator):
    """Context decorator that logs the execution time of the decorated item.

    Parameters
    ----------
    arg: object or str
        If `arg` type is `str`, a new decorator is returned which uses `arg`
        in the generated message in places of the name of the decorated object.
    """

    def __new__(cls, arg):
        if callable(arg):
            return cls(arg.__name__)(arg)
        return super().__new__(cls)

    def __init__(self, msg):
        self.msg = msg
        self.logger = logging.getLogger("timeit")

    def __enter__(self):
        self.logger.debug("{} ...".format(self.msg))
        self._start = time.time()

    def __exit__(self, *args):
        elapsed = time.time() - self._start
        self.logger.debug(
                "{} done in {}".format(
                    self.msg, _format_time(elapsed)))


class logit(ContextDecorator):
    """Decorator that logs the execution of the decorated item.

    Parameters
    ----------
    log: callable
        The logging function to use.

    msg: str
        The message body to use.
    """

    def __init__(self, log, msg):
        self.log = log
        self.msg = msg

    def __enter__(self):
        self.log(f"{self.msg} ...")

    def __exit__(self, *args):
        self.log(f'{self.msg} done')


# @contextmanager
# def scoped_loglevel(level=logging.INFO):
#     """
#     A context manager that will prevent any logging messages
#     triggered during the body from being processed.
#     """

#     previous_level = logging.root.manager.disable

#     logging.disable(level)

#     try:
#         yield
#     finally:
#         logging.disable(previous_level)


@contextmanager
def disable_logger(*names):
    """Temporarily disable a specific logger."""
    old_values = dict()
    for name in names:
        logger = logging.getLogger(name)
        old_values[logger] = logger.disabled
        logger.disabled = True
    try:
        yield
    finally:
        for name in names:
            logger = logging.getLogger(name)
            logger.disabled = old_values[logger]


def logged_dict_update(log_func, l, r):
    """Update a dict with any changes tracked via `log_func`."""
    for k, v in r.items():
        if k in l and l[k] != v:
            log_func(
                    f"entry changed"
                    f" {k} {l[k]} -> {v}")
        l[k] = v
    return l
