#! /usr/bin/env python

from contextlib import ContextDecorator
import logging
import logging.config
import inspect
import functools
import time
from astropy.utils.console import human_time
import copy

from ..misc import rupdate

try:
    from . import console_color
except ModuleNotFoundError:
    console_color = None


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
        colored=console_color is not None,
        **kwargs):
    """Initialize logging with some sensible presets.

    Parameters
    ----------
    level: str
        The log level to use.

    file_: str, optional
        If set, the log are saved in `file_`.

    colored: bool
        If set to True, console messages will be colored (requires package
        `click` to work).

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
    if colored and console_color is None:
        colored = False
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


def timeit(arg):
    """Decorator that logs the execution time of the decorated item.

    Parameters
    ----------
    arg: object or str
        If `arg` type is `str`, a new decorator is returned which uses `arg`
        in the generated message in places of the name of the decorated object.
    """

    if isinstance(arg, str):
        funcname = arg

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                logger = logging.getLogger("timeit")
                logger.debug("{} ...".format(funcname))
                s = time.time()
                r = func(*args, **kwargs)
                elapsed = time.time() - s
                logger.debug("{} done in {}".format(
                    funcname, _format_time(elapsed)))
                return r
            return wrapper
        return decorator
    else:
        return timeit(arg.__name__)(arg)


class Timer(object):
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
