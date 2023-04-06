import numpy as np

from .log import logger

__all__ = ["flex_reshape", "make_complex"]


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
