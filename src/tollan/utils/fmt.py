"""
Formatting utilities for YAML, masks, and bitmasks.

Includes pretty-printing for YAML, numpy masks, and Flag-based bitmasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import pyaml

from .yaml import add_numpy_scalar_representers

if TYPE_CHECKING:
    from enum import Flag

    import numpy.typing as npt

__all__ = [
    "BitmaskStats",
    "bitmask_stats",
    "pformat_bitmask",
    "pformat_fancy_index",
    "pformat_mask",
    "pformat_yaml",
]

add_numpy_scalar_representers(pyaml.PYAMLDumper)
pyaml.add_representer(None, lambda s, d: s.represent_str(str(d)))  # type: ignore[arg-type]


def pformat_yaml(obj: Any) -> str:
    """
    Pretty-format an object as a YAML string.

    If the object has a __wrapped__ attribute, formats the wrapped object instead.

    Example
    -------
    >>> data = {'a': 1, 'b': [2, 3]}
    >>> print(pformat_yaml(data))
    a: 1
    b:
        - 2
        - 3
    """
    if hasattr(obj, "__wrapped__"):
        # unwrap if has wrapped interface
        obj = obj.__wrapped__
    return f"\n{pyaml.dump(obj)}"


def pformat_fancy_index(
    arg: slice | npt.ArrayLike | list[slice | npt.ArrayLike],
) -> str:
    """
    Pretty-format a numpy fancy index, slice, or mask.

    Examples
    --------
    >>> pformat_fancy_index(slice(1, 10, 2))
    '[1:10:2]'
    >>> pformat_fancy_index(slice(None, 5))
    '[:5]'
    >>> import numpy as np
    >>> mask = np.array([True, False, True, True])
    >>> pformat_fancy_index(mask)
    '<mask 3/4>'
    >>> pformat_fancy_index([slice(0, 2), slice(3, 5)])
    '[[0:2], [3:5]]'
    """
    if isinstance(arg, slice):
        start = "" if arg.start is None else arg.start
        stop = "" if arg.stop is None else arg.stop
        result = f"[{start}:{stop}{{}}]"
        if arg.step is None or arg.step == 1:
            result = result.format("")
        else:
            result = result.format(f":{arg.step}")
        return result
    if isinstance(arg, np.ndarray):
        return f"<mask {np.sum(arg)}/{arg.size}>"
    if isinstance(arg, list):
        s = ", ".join(pformat_fancy_index(a) for a in arg)  # ty: ignore[invalid-argument-type]
        return f"[{s}]"
    return str(arg)


def _pformat_mask(g: int, n: int, p: float) -> str:
    return f"{g}/{n} ({p:.2%})"


def pformat_mask(mask: npt.NDArray[np.bool_]) -> str:
    """
    Pretty-format a boolean mask as 'selected/total (percentage)'.

    Example
    -------
    >>> import numpy as np
    >>> mask = np.array([True, False, True, True, False])
    >>> pformat_mask(mask)
    '3/5 (60.00%)'
    """
    g = mask.sum()
    n = mask.size
    p = g / n
    return _pformat_mask(g, n, p)


def bitmask_stats(bm_cls: type[Flag], bitmask: npt.NDArray) -> pd.DataFrame:
    """
    Compute statistics for each flag in a bitmask.

    Returns a DataFrame with columns: name, selected, total, frac, summary.
    """
    records = []
    for name, value in bm_cls.__members__.items():
        m = (bitmask & value.value) > 0
        g = m.sum()
        n = m.size
        # Avoid division by zero warning when n=0
        p = g / n if n > 0 else float("nan")
        records.append(
            {
                "name": name,
                "selected": g,
                "total": n,
                "frac": p,
                "summary": _pformat_mask(g, n, p),
            },
        )
    return pd.DataFrame.from_records(records)


@dataclass
class BitmaskStats:
    """
    Compute and format statistics for bitmask flags.

    Use .pformat() for a summary table.

    Example
    -------
    >>> from enum import Flag, auto
    >>> import numpy as np
    >>> class Status(Flag):
    ...     OK = auto()
    ...     WARNING = auto()
    ...     ERROR = auto()
    >>> bitmask = np.array([1, 3, 5, 7])
    >>> stats = BitmaskStats(Status, bitmask)
    >>> print(stats.pformat())
    name     summary
    OK       4/4 (100.00%)
    WARNING  2/4 (50.00%)
    ERROR    2/4 (50.00%)
    """

    bm_cls: type[Flag]
    bitmask: npt.NDArray

    def __post_init__(self) -> None:
        """Compute statistics after initialization."""
        self._stats = bitmask_stats(self.bm_cls, self.bitmask)

    @property
    def stats(self) -> pd.DataFrame:
        """Get the statistics table.

        Returns
        -------
        DataFrame
            Table with columns: name, selected, total, frac, summary
        """
        return self._stats

    def pformat(self) -> str:
        """Format statistics as string table.

        Returns
        -------
        str
            Pretty-formatted table showing name and summary columns
        """
        return self.stats.to_string(columns=("name", "summary"), index=False)


def pformat_bitmask(bm_cls: type[Flag], bitmask: npt.NDArray) -> str:
    """
    Pretty-format bitmask statistics as a summary table.

    Example
    -------
    >>> from enum import Flag, auto
    >>> import numpy as np
    >>> class Status(Flag):
    ...     OK = auto()
    ...     WARNING = auto()
    ...     ERROR = auto()
    >>> bitmask = np.array([1, 3, 5, 7])
    >>> print(pformat_bitmask(Status, bitmask))
    name     summary
    OK       4/4 (100.00%)
    WARNING  2/4 (50.00%)
    ERROR    2/4 (50.00%)
    """
    return BitmaskStats(bm_cls, bitmask).pformat()
