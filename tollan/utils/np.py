#! /usr/bin/env python

from .log import get_logger
import numpy as np


__all__ = ['flex_reshape', ]


def flex_reshape(arr, shape):
    """Reshape an array with possible trimming of extraneous items."""
    logger = get_logger()
    shape = list(shape)
    if -1 in shape:
        iauto = shape.index(-1)
        shape.remove(-1)
        if -1 in shape:
            raise ValueError("only one dim can be -1")
        n = np.prod(shape)
        shape.insert(iauto, arr.size // n)
    n = np.prod(shape)
    logger.debug(f"flex reshape {arr.shape} -> {shape}")
    return arr.reshape(-1)[:n].reshape(shape)
