#! /usr/bin/env python

from ..sys import get_user_data_dir
from ..log import get_logger, logit


__all__ = ['get_wraps_dir', ]


def get_wraps_dir():
    """Return the directory for saving wrappers."""
    logger = get_logger()
    p = get_user_data_dir().joinpath('wraps')
    if not p.exists():
        with logit(logger.debug, f"create {p}"):
            p.mkdir(exist_ok=True, parents=True)
    return p
