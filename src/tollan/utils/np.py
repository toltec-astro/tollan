import functools

import astropy.units as u
import numpy as np

from .log import logger

__all__ = [
    "flex_reshape",
    "make_complex",
    "strip_unit",
    "attach_unit",
    "preserve_unit",
    "qrange",
]


def flex_reshape(arr, shape, trim_option="end"):
    """Reshape an array with possible trimming of extraneous items.

    Parameters
    ----------
    arr : `numpy.ndarray`
        The array to reshape

    shape : tuple
        The new shape.

    trim_option : str:
        The way to trim the original shape, can be one of "start" or "end".
    """
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
    if trim_option == "end":
        s = slice(None, n)
    elif trim_option == "start":
        s = slice(-n, None)
    else:
        raise ValueError("invalid trim option.")
    return arr.reshape(-1)[s].reshape(shape)


def make_complex(real_part, imag_part):
    """Create complex array from the real and imaginary parts."""
    if real_part.shape != imag_part.shape:
        raise ValueError("real and imaginary parts have to be of the same shape.")
    result = np.empty(real_part.shape, dtype=complex)
    result.real = real_part
    result.imag = imag_part
    return result


def strip_unit(arr):
    """Remove unit from array."""
    if isinstance(arr, u.Quantity):
        return arr.value, arr.unit
    if isinstance(arr, np.ma.MaskedArray):
        return np.ma.array(arr.data.value, mask=arr.mask), arr.data.unit
    return arr, None


def attach_unit(arr, unit):
    """Attach unit to array."""
    if unit is not None:
        if isinstance(arr, np.ma.MaskedArray):
            return np.ma.array(arr.data << unit, mask=arr.mask)
        return arr << unit
    return arr


def preserve_unit(f):
    """Preserve unit of first argument passed to function."""

    @functools.wraps(f)
    def wrapper(d, *a, **k):
        dv, unit = strip_unit(d)
        v = f(dv, *a, **k)
        return attach_unit(v, unit)

    return wrapper


def ensure_unit(arr, unit) -> u.Quantity:
    """Ensure the data have given unit."""
    if arr is None:
        return arr
    return arr << unit


def qrange(x0, x1, step):
    """Return arange for quantity."""
    x0_value, x_unit = strip_unit(x0)
    if x_unit is None:
        x1_value = x1
        step_value = step
    else:
        x1_value = x1.to_value(x_unit)
        step_value = step.to_value(step)
    return attach_unit(np.arange(x0_value, x1_value, step_value), x_unit)
