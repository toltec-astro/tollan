# Licensed under a 3-clause BSD style license - see LICENSE.rst

import appdirs
from pathlib import Path


_excluded_from_all = set(globals().keys())


def get_pkg_data_path():
    """Return the package data path."""
    return Path(__file__).parent.parent.joinpath("data")


def get_user_data_dir():
    return Path(appdirs.user_data_dir('tollan', 'toltec'))


from .misc import *  # noqa: F401, F403, E402


__all__ = list(set(globals().keys()).difference(_excluded_from_all))
