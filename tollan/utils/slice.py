#! /usr/bin/env python

import re
import copy


__all__ = [
        'BoundedSliceChain', 'UnboundedSliceChain',
        'resolve_slice', 'XLoc',
        'parse_slice',
        ]


class SliceChain(object):
    bounded = NotImplemented


class BoundedSliceChain(SliceChain):
    """A chain of slices, with known array size.

    Parameters
    ----------
    range_: range
        The initial index generator.
    _n: list of int, optional
        The intended array size (not enforced).
    """

    bounded = True

    def __init__(self, range_, n=None):
        self._range = range_

        self._ns = set([len(self)])
        if isinstance(n, int):
            self._ns.add(n)

    def __getitem__(self, slice_):
        ss = BoundedSliceChain(self._range[slice_])
        ss._ns = ss._ns.union(self._ns)
        return ss

    def apply(self, arr):
        r = self._range
        return arr[slice(r.start, r.stop, r.step)]

    def __len__(self):
        r = self._range
        return len(r)

    def __repr__(self):
        r = self._range
        ns = sorted(list(self._ns), reverse=True)

        def fmt_range(r):
            return f"({r.start}, {r.stop}, {r.step})"

        ns = ' -> '.join(map(str, ns))
        return f"{self.__class__.__name__}" \
               f"{fmt_range(r)}({ns})"

    def to_slice(self):
        r = self._range
        return slice(r.start, r.stop, r.step)


class UnboundedSliceChain(SliceChain):
    """A chain of slices.

    Parameters
    ----------
    slices: slice or a list of slices, optional
        This is used to initialize the slice chain.
    """

    def __init__(self, slices=None):
        if isinstance(slices, slice):
            slices = [slices]
        elif slices is None:
            slices = [slice(None)]
        self._slices = list(slices)

    def __copy__(self):
        return self.__class__(copy.copy(self._slices))

    def __getitem__(self, s):
        """Return a new slice chain instance.
        """
        ss = copy.copy(self)
        ss._slices.append(s)
        return ss

    def apply(self, arr):
        _arr = arr
        for s in self._slices:
            _arr = _arr[s]
        return _arr

    def resolve(self, other, **kwargs):
        """Return a bounded slice chain by operating on `other`."""
        if not isinstance(other, BoundedSliceChain):
            result = BoundedSliceChain(other, **kwargs)
        else:
            result = other
        for s in self._slices:
            result = result[s]
        return result

    def __repr__(self):
        return f"{self.__class__.__name__}(unbounded)"


def resolve_slice(slice_, n):
    """Return a bounded slice given length `n`."""
    return slice(*slice_.indices(n))


class XLoc(object):
    """
    This provides a interface similar to that of pandas `DataFrame.xloc`.

    The wrapped function shall take an index or slice object and return the
    sliced entity.

    Additional arguments and keyword arguments can be passed through the
    ``__call__`` method, however these will be invalidated as soon as
    the ``__getitem__`` is called.

    Parameters
    ----------
    func: callable
        The function that implements the slice logic.
    """

    def __init__(self, func):
        self._func = func
        self._reset_extra_args()

    def _reset_extra_args(self):
        self._extra_args = tuple(), dict()

    def _update_extra_args(self, args, kwargs):
        args0, kwargs0 = self._extra_args
        kwargs0.update(**kwargs)
        self._extra_args = args0 + tuple(args), kwargs0

    def _pop_extra_args(self):
        args, kwargs = self._extra_args
        self._reset_extra_args()
        return args, kwargs

    def __getitem__(self, *args):
        ex_args, ex_kwargs = self._pop_extra_args()
        return self._func(
                *args, *ex_args, **ex_kwargs)

    def __call__(self, *args, **kwargs):
        """Store kwargs to be passed to the wrapped function."""
        self._update_extra_args(args, kwargs)
        return self


def parse_slice(slice_str):
    """Return a slice object from string."""

    re_slice = re.compile(
        r'^(?P<start>[+-]?\d+)?(?P<is_slice>:)?'
        r'(?P<stop>[+-]?\d+)?:?(?P<step>[+-]?\d+)?$'
        )
    m = re.match(re_slice, slice_str)
    if not m:
        return slice(None)
    g = m.groupdict()

    def get(key):
        val = g.get(key, None)
        if val is not None:
            return int(val)
        return val
    start, stop, step = map(get, ("start", "stop", "step"))
    is_slice = g.get('is_slice', None) is not None
    if is_slice:
        return slice(start, stop, step)
    elif start is not None:
        # return start
        if start == -1:
            end = None
        else:
            end = start + 1
        return slice(start, end)
    return slice(None)
