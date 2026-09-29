"""Slice notation utilities."""

from __future__ import annotations

import re

__all__ = ["parse_slice"]

_SLICE_PATTERN = re.compile(
    r"(?P<start>[+-]?\d+)?"
    r"(?:(?P<is_slice>:)(?P<stop>[+-]?\d+)?"
    r"(?::(?P<step>[+-]?\d+)?)?)?"
)


def parse_slice(slice_str: str) -> slice:
    """Parse a slice or single index from text.

    Parameters
    ----------
    slice_str : str
        An integer or ``start:stop[:step]``, without brackets or whitespace.
        Bounds and steps may be signed, and omitted components remain None.
        An empty string, ``:`` or ``::`` selects the entire sequence.

    Returns
    -------
    slice
        The requested slice. A single index produces a one-element slice,
        preserving the sliced axis. Bounds are not resolved against a length;
        applying the slice uses normal Python clipping and negative indexing.

    Raises
    ------
    ValueError
        If the text is malformed or the step is zero.
    TypeError
        If the input is not a string.

    Examples
    --------
    >>> parse_slice("1:10:2")
    slice(1, 10, 2)
    >>> parse_slice("7")
    slice(7, 8, None)
    >>> parse_slice("-1")
    slice(-1, None, None)
    >>> list(range(5))[parse_slice("::-1")]
    [4, 3, 2, 1, 0]
    >>> list(range(*parse_slice(":3").indices(10)))
    [0, 1, 2]
    """
    match = _SLICE_PATTERN.fullmatch(slice_str)
    if match is None:
        msg = f"Invalid slice: {slice_str!r}"
        raise ValueError(msg)
    start, stop, step = (
        int(value) if value is not None else None
        for value in match.group("start", "stop", "step")
    )
    if step == 0:
        msg = "Slice step cannot be zero"
        raise ValueError(msg)
    if match["is_slice"] is None and start is not None:
        stop = None if start == -1 else start + 1
    return slice(start, stop, step)
