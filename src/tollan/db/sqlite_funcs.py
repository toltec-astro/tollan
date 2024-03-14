import numpy as np


class AggregateBase:
    """A base class for aggregate functions."""

    def __init__(self):
        self.values = []

    def step(self, value):  # noqa: D102
        self.values.append(value)

    def finalize(self):  # noqa: D102
        return NotImplemented


class BitwiseAnd(AggregateBase):
    """Bitwise and."""

    def finalize(self):  # noqa: D102
        return int(np.bitwise_and.reduce(self.values))


class BitwiseOr(AggregateBase):
    """Bitwise Or."""

    def finalize(self):  # noqa: D102
        return int(np.bitwise_or.reduce(self.values))


aggregates = [
    ("bit_or", 1, BitwiseOr),
    ("bit_and", 1, BitwiseAnd),
]


functions = []
