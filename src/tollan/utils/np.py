"""
NumPy and astropy.units utility functions.

Unified helpers for NumPy arrays and astropy quantities.
Includes unit handling, reshaping, and complex array creation.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Literal

    import numpy.typing as npt

import astropy.units as u
import numpy as np

from .log import logger

__all__ = [
    "attach_unit",
    "ensure_unit",
    "flex_reshape",
    "make_complex",
    "preserve_unit",
    "qrange",
    "strip_unit",
]


def flex_reshape(
    arr: npt.NDArray,
    shape: Sequence[int],
    trim_option: Literal["end", "start"] = "end",
) -> npt.NDArray:
    """
    Reshape an array, trimming elements if needed.

    Parameters
    ----------
    arr : ndarray
        Array to reshape.
    shape : sequence of int
        New shape (may include one -1 for auto size).
    trim_option : {'end', 'start'}, optional
        Trim from end or start if needed (default: 'end').

    Returns
    -------
    ndarray
        Reshaped array.

    Examples
    --------
    >>> import numpy as np
    >>> arr = np.arange(10)
    >>> flex_reshape(arr, (2, 4))
    array([[0, 1, 2, 3],
           [4, 5, 6, 7]])
    """
    shape = list(shape)
    if -1 in shape:
        iauto = shape.index(-1)
        shape.remove(-1)
        if -1 in shape:
            msg = "only one dim can be -1"
            raise ValueError(msg)
        n = int(np.prod(shape))
        shape.insert(iauto, arr.size // n)
    n = int(np.prod(shape))
    logger.debug(f"flex reshape {arr.shape} -> {shape}")
    if trim_option == "end":
        s = slice(None, n)
    elif trim_option == "start":
        s = slice(-n, None)
    else:
        msg = "invalid trim option."
        raise ValueError(msg)
    return arr.reshape(-1)[s].reshape(shape)


def make_complex(
    real_part: npt.NDArray,
    imag_part: npt.NDArray,
) -> npt.NDArray[np.complexfloating]:
    """Create a complex array from real and imaginary parts.

    Parameters
    ----------
    real_part : ndarray
        Real component of the complex array
    imag_part : ndarray
        Imaginary component of the complex array

    Returns
    -------
    ndarray[complexfloating]
        Complex array with specified real and imaginary parts

    Raises
    ------
    ValueError
        If real and imaginary parts have different shapes
    """
    if real_part.shape != imag_part.shape:
        msg = "real and imaginary parts have to be of the same shape."
        raise ValueError(msg)
    result = np.empty(real_part.shape, dtype=complex)
    result.real = real_part
    result.imag = imag_part
    return result


UnitT = u.UnitBase | u.StructuredUnit


@overload
def strip_unit(arr: np.ma.MaskedArray) -> tuple[np.ma.MaskedArray, UnitT | None]: ...


@overload
def strip_unit(arr: u.Quantity) -> tuple[npt.ArrayLike, UnitT]: ...


@overload
def strip_unit(arr: npt.ArrayLike) -> tuple[npt.ArrayLike, UnitT | None]: ...


def strip_unit(
    arr: npt.ArrayLike | u.Quantity,
) -> tuple[npt.ArrayLike, UnitT | None]:
    """
    Remove unit from array, returning (data, unit).

    Parameters
    ----------
    arr : ArrayLike | Quantity
        Input array (may have astropy units)

    Returns
    -------
    tuple[ArrayLike, UnitT | None]
        Tuple of (data array without units, unit or None)

    Examples
    --------
    >>> import numpy as np
    >>> import astropy.units as u
    >>> q = np.arange(3) * u.m
    >>> arr = np.ma.array(q, mask=[0, 1, 0])
    >>> data, unit = strip_unit(arr)
    >>> data  # doctest: +SKIP
    masked_array(data=[0, --, 2], mask=[False,  True, False], fill_value=1e+20)
    >>> unit
    Unit("m")
    """
    if isinstance(arr, u.Quantity):
        return arr.value, arr.unit
    if isinstance(arr, np.ma.MaskedArray):
        if hasattr(arr.data, "value") and hasattr(arr.data, "unit"):
            return np.ma.array(arr.data.value, mask=arr.mask), arr.data.unit
        return arr, None
    return arr, None


@overload
def attach_unit(arr: npt.NDArray, unit: UnitT) -> u.Quantity: ...


@overload
def attach_unit(
    arr: npt.ArrayLike | np.ma.MaskedArray,
    unit: None,
) -> npt.ArrayLike | np.ma.MaskedArray: ...


def attach_unit(
    arr: npt.ArrayLike | np.ma.MaskedArray,
    unit: UnitT | None,
) -> npt.ArrayLike | np.ma.MaskedArray | u.Quantity:
    """Attach a unit to an array if unit is not None.

    Parameters
    ----------
    arr : ArrayLike | MaskedArray
        Array to attach unit to
    unit : UnitT | None
        Astropy unit to attach (or None for no-op)

    Returns
    -------
    ArrayLike | MaskedArray | Quantity
        Array with unit attached (or original if unit is None)
    """
    if unit is not None:
        if isinstance(arr, np.ma.MaskedArray):
            return np.ma.array(arr.data << unit, mask=arr.mask)
        return arr << unit
    return arr


def preserve_unit[F: Callable](f: F) -> F:
    """Strip unit from first argument, reattach to result.

    Parameters
    ----------
    f : Callable
        Function to wrap (first arg will have units stripped/reattached)

    Returns
    -------
    F
        Wrapped function preserving units
    """

    @functools.wraps(f)
    def wrapper(d: Any, *a: Any, **k: Any) -> Any:
        """Strip unit, call function, reattach unit.

        Parameters
        ----------
        d : Any
            First argument (may have units attached)
        *a
            Additional positional arguments
        **k
            Additional keyword arguments

        Returns
        -------
        Any
            Result with units reattached
        """
        dv, unit = strip_unit(d)
        v = f(dv, *a, **k)
        return attach_unit(v, unit)

    return wrapper  # type: ignore[return-value]


@overload
def ensure_unit(
    arr: npt.NDArray | u.Quantity,
    unit: UnitT,
) -> u.Quantity: ...


@overload
def ensure_unit(
    arr: None,
    unit: UnitT,
) -> None: ...


def ensure_unit(
    arr: npt.ArrayLike | u.Quantity | None,
    unit: UnitT,
) -> u.Quantity | None:
    """Ensure data has the given unit (returns None if arr is None).

    Parameters
    ----------
    arr : ArrayLike | Quantity | None
        Input array (with or without units)
    unit : UnitT
        Target unit to apply

    Returns
    -------
    Quantity | None
        Array with specified unit, or None if input is None
    """
    if arr is None:
        return arr
    return arr << unit


def qrange(
    x0: u.Quantity,
    x1: u.Quantity,
    step: u.Quantity,
) -> u.Quantity:
    """Like numpy.arange, but for astropy quantities (unit-aware).

    Parameters
    ----------
    x0 : Quantity
        Start value with units
    x1 : Quantity
        End value with units (exclusive)
    step : Quantity
        Step size with units

    Returns
    -------
    Quantity
        Array of values from x0 to x1 with step increments
    """
    x0_value, x_unit = strip_unit(x0)
    if x_unit is None:
        x1_value = x1
        step_value = step
    else:
        x1_value = x1.to_value(x_unit)
        step_value = step.to_value(x_unit)
    return attach_unit(
        np.arange(x0_value, x1_value, step_value),  # ty: ignore[no-matching-overload]
        x_unit,
    )
