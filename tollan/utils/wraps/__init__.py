#! /usr/bin/env python

from .. import get_user_data_dir
from ..log import get_logger, logit


def get_wraps_dir():
    logger = get_logger()
    p = get_user_data_dir().joinpath('wraps')
    if not p.exists():
        with logit(logger.debug, f"create {p}"):
            p.mkdir(exist_ok=True, parents=True)
    return p
