#! /usr/bin/env python

from contextlib import ContextDecorator, AbstractContextManager
import logging
import logging.config
import inspect
import time
import copy
from pathlib import Path
from wrapt import ObjectProxy
from contextlib import contextmanager
from astropy.utils.console import human_time
from ..misc import rupdate
from . import console_color


__all__ = ['init_log', 'log_to_file', 'get_logger', 'timeit', 'logit']


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
            'numba': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
                },
            'astropy': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
                },
            },
        'root': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': False
            },
        },
    }


dict_config = ObjectProxy(None)
"""
A proxy to the `~logging.config.dictConfigClass` instance, which is made
available after `init_log` is called.
"""


def init_log(
        preset='default', level='INFO',
        filepath=None, colored=True, **kwargs):
    """Initialize logging with some sensible presets.

    Parameters
    ----------
    preset : str
        The predefined dict config to use.

    level : str
        The log level to use.

    filepath : str, `pathlib.Path`, optional
        If set, the log are saved in `filepath`.

    colored : bool
        If set to True, console messages will be colored.

    **kwargs
        Update the preset with entries in this dict.

    """
    config = copy.deepcopy(presets[preset])
    if filepath is not None:
        rupdate(config, {
            'handlers': {'logfile': {
                    'class': 'logging.FileHandler',
                    'formatter': "standard",
                    'filename': filepath.as_posix()
                    },
                },
            'loggers': {
                '': {'handlers': ['logfile', ]},
                'root': {'handlers': ['logfile', ]},
                },
            })
    if colored:
        # this will replace the default handler with colored output handler
        rupdate(config, console_color.config)
    # merge any user settings
    rupdate(config, kwargs)
    # set levels for each handlers
    # note we avoid setting the level for the root logger, which
    # will override the per-handler settings
    for h in config['handlers'].values():
        h['level'] = level
    # we save the config so we can access the sensibles later
    dict_config.__wrapped__ = logging.config.dictConfigClass(config)
    dict_config.configure()


def _find_logfile_handler(handlers, filepath):
    """Find from the list of handlers the one that log to given `filepath`"""
    for handler in handlers:
        if isinstance(handler, logging.FileHandler):
            if Path(handler.baseFilename).samefile(filepath):
                return handler
    return None


def add_logfile_handler(
        logger, filepath, level='DEBUG', formatter=None):
    """Add a handler to logger to log to `filepath`."""
    filepath = Path(filepath)
    h = _find_logfile_handler(logger.handlers, filepath)
    if h is None:
        # create logfile handler
        if formatter is None:
            formatter = presets['default']['formatters']['standard']
        if isinstance(formatter, dict):
            f = dict_config.configure_formatter(formatter)
        else:
            f = formatter
        h = logging.FileHandler(
                filename=filepath.as_posix(),
                )
        h.setFormatter(f)
        logger.addHandler(h)
    return h


def remove_logfile_handler(logger, filepath, level='DEBUG'):
    """Remove the handler from logger to log to `filepath`."""
    filepath = Path(filepath)
    h = _find_logfile_handler(logger.handlers, filepath)
    if h is not None:
        logger.removeHandler(h)


class log_to_file(AbstractContextManager):
    """A context manager to log to file.

    Parameters
    ----------
    filepath : str, `pathlib.Path`, optional
        The log file path.
    logger : `logging.Logger`, optional
        The logger to log to file. If None, the root logger is used.
    level : str
        The log level.
    disable_other_handlers : bool
        If True, other handlers will be disabled. It will be restored
        at exit.
    """

    def __init__(
            self, filepath, logger=None, level='DEBUG',
            disable_other_handlers=False):
        self._filepath = Path(filepath)
        self._logger = logger or get_logger('')
        self._level = level
        self._disable_other_handlers = disable_other_handlers

    def __enter__(self):
        logger = self._logger
        logfile_handler = self._logfile_handler = add_logfile_handler(
                logger=logger, filepath=self._filepath,
                level=self._level)
        if self._disable_other_handlers:
            original_handlers = self._original_handlers = list()
            for h in logger.handlers:
                if h is not logfile_handler:
                    original_handlers.append(h)
            for h in original_handlers:
                logger.removeHandler(h)

    def __exit__(self, *exc_info):
        logger = self._logger
        logger.removeHandler(self._logfile_handler)
        if self._disable_other_handlers:
            for h in self._original_handlers:
                self._logger.addHandler(h)


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

    def __new__(cls, arg, **kwargs):
        if callable(arg):
            return cls(arg.__name__, **kwargs)(arg)
        return super().__new__(cls)

    def __init__(self, msg, level='DEBUG'):
        self.msg = msg
        self.logger = logging.getLogger("timeit")
        self._level = logging.getLevelName(level)

    def __enter__(self):
        self.logger.log(self._level, "{} ...".format(self.msg))
        self._start = time.time()

    def __exit__(self, *args):
        elapsed = time.time() - self._start
        self.logger.log(
                self._level,
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


def logged_dict_update(log_func, left, right):
    """Update a dict with any changes tracked via `log_func`."""
    for k, v in right.items():
        if k in left and left[k] != v:
            log_func(
                    f"entry changed"
                    f" {k} {left[k]} -> {v}")
        left[k] = v
    return left


class logged_closing(AbstractContextManager):
    """A slightly modified version of `contextlib.closing` with logging."""

    def __init__(self, log, thing, msg=None):
        self.log = log
        self.thing = thing

        if msg is None:
            msg = f'close {self.thing}'
        self.msg = msg

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):

        with logit(self.log, self.msg):
            self.thing.close()
