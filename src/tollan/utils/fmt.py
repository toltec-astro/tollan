from dataclasses import dataclass
from enum import Flag

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyaml

__all__ = [
    "pformat_yaml",
    "pformat_fancy_index",
    "pformat_mask",
    "bitmask_stats",
    "BitmaskStats",
    "pformat_bitmask",
]

pyaml.add_representer(np.float64, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.float32, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.int32, lambda s, d: s.represent_int(d))
pyaml.add_representer(np.int64, lambda s, d: s.represent_int(d))
pyaml.add_representer(None, lambda s, d: s.represent_str(str(d)))


def pformat_yaml(obj):
    """Return object as pretty-formatted string."""
    if hasattr(obj, "__wrapped__"):
        # unwrap if has wrapped interface
        obj = obj.__wrapped__
    return f"\n{pyaml.dump(obj)}"


def pformat_fancy_index(arg):
    """Return pretty-formated index or slice."""
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
        s = ", ".join(pformat_fancy_index(a) for a in arg)
        return f"[{s}]"
    return arg


def _pformat_mask(g, n, p):
    return f"{g}/{n} ({p:.2%})"


def pformat_mask(mask):
    """Return pretty-formatted boolean mask."""
    g = mask.sum()
    n = mask.size
    p = g / n
    return _pformat_mask(g, n, p)


def bitmask_stats(bm_cls, bitmask):
    """Return a table contains basic stats of bitmask."""
    records = []
    for name, value in bm_cls.__members__.items():
        m = (bitmask & value) > 0
        g = m.sum()
        n = m.size
        p = g / n
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
    """A class to compute bitmask stats."""

    bm_cls: Flag
    bitmask: npt.NDArray

    def __post_init__(self):
        self._stats = bitmask_stats(self.bm_cls, self.bitmask)

    @property
    def stats(self):
        """The stats table."""
        return self._stats

    def pformat(self):
        """Return the pretty-formated stats."""
        return self.stats.to_string(columns=("name", "summary"), index=False)


def pformat_bitmask(bm_cls, bitmask):
    """Return pretty-formatted."""
    return BitmaskStats(bm_cls, bitmask).pformat()
