#! /usr/bin/env python

import copy


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

    def bound_to(self, other, **kwargs):
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
