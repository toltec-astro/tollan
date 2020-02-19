#! /usr/bin/env python


import numpy as np


class DataFrameRing(object):
    """This class provide a fixed size data frame with ring buffer semantics.
    """

    def __init__(self, capacity, columns=None):
        self.resize(capacity, columns)

    def resize(self, capacity, columns=None):
        """Resize the ring buff. The data will lost."""
        self._capacity = capacity
        self._columns = columns
        self._data = None
        self._get_idx = 0
        self._put_idx = 0
        self._full = False

    @staticmethod
    def _put_may_wrap(data, idx, df):
        cap = data.shape[0]
        n_rows = df.shape[0]
        assert n_rows <= cap

        new_idx = (idx + n_rows) % cap
        assert new_idx != idx
        if new_idx > idx:
            # no wrap
            assert n_rows == new_idx - idx
            data.iloc[idx:new_idx] = df
        else:
            # wrap
            data.iloc[idx:] = df.iloc[:-new_idx]
            data.iloc[:new_idx] = df.iloc[-new_idx:]
        return data, new_idx

    def put(self, df):
        """Put `df` in the ring.

        The get head may be moved to make space for the operation.

        If `df` exceeds the capacity, the buffer will be reset with
        the tail of `df`.
        """
        n_rows = df.shape[0]
        cap = self._capacity
        gidx = self._get_idx
        pidx = self._put_idx

        if n_rows >= cap:
            # need to truncate the data
            self.resize(cap, columns=df.columns)
            self._data = df.tail(cap)
            self._full = True
            return self

        if self._full:
            # ring is full
            assert gidx == pidx
            assert self._data.shape[0] == cap
            idx = gidx
            data, new_idx = self._put_may_wrap(self._data, idx, df)
            self._data = data
            self._get_idx = self._put_idx = new_idx
            self._full = True
            return self

        # ring not full
        assert gidx == 0
        diff = pidx - gidx
        assert diff >= 0
        if diff == 0:
            space = cap
        else:  # diff > 0
            space = cap - diff

        # no data yet
        if space == cap:
            assert self._data is None
            assert pidx == 0
            self._columns = df.columns
            self._data = df
            self._get_idx = gidx
            self._put_idx = pidx + n_rows
            self._full = False
            return self

        # have some data already
        assert self._data is not None

        if n_rows <= space:
            # will not overflow
            self._data.append(df)
            self._get_idx = 0
            self._put_idx = self._data.shape[0] % cap
            if n_rows == space:
                assert self._put_idx == 0
                self._full = True
            else:
                self._full = False
            return self

        # will overflow
        n_overflow = n_rows - space
        assert n_overflow > 0
        # fill up to cap first
        self._data.append(df.iloc[:-n_overflow])
        assert self._data.shape[0] == cap
        # overwrite the head with overflowed
        self._data.iloc[:n_overflow] = df.iloc[-n_overflow:]
        self._get_idx = self._put_idx = n_overflow
        self._full = True
        return self

    def get(self):
        """Get df from the ring."""
        gidx = self._get_idx
        pidx = self._put_idx
        cap = self._capacity
        assert gidx <= pidx
        if self._full:
            assert gidx == pidx
            if gidx == 0:
                return self._data
            return self._data.iloc[np.arange(cap).roll(gidx)]
        # not full
        assert gidx == 0
        assert self._data.shape[0] < cap
        return self._data

    @property
    def columns(self):
        if self._data is None:
            return None
        return self._data.columns

    def __len__(self):
        """return size (not size_max)"""
        if self._data is None:
            return 0
        return self._data.shape[0]

    def __repr__(self):
        return f"{self.__class__}({self._capacity}, isfull={self._full})"
