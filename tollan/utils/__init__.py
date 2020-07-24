# Licensed under a 3-clause BSD style license - see LICENSE.rst

import appdirs
from pathlib import Path


def get_pkg_data_path():
    """Return the package data path."""
    return Path(__file__).parent.parent.joinpath("data")


def get_user_data_dir():
    return Path(appdirs.user_data_dir('tollan', 'toltec'))


from .misc import *  # noqa: F401, F403
