"""Axes ownership and artist preservation when moving between figures."""

import matplotlib as mpl
import numpy as np
import pytest

mpl.use("Agg")

from matplotlib import pyplot as plt

from tollan.plot.mpl import move_axes


@pytest.mark.parametrize("remove", [False, True])
def test_move_axes_retains_artists_and_replaces_destination(remove):
    original, ax = plt.subplots()
    destination, placeholder = plt.subplots()
    try:
        (line,) = ax.plot([1, 2], [3, 4])
        position = placeholder.get_position().bounds

        result = move_axes(ax, placeholder, remove=remove)

        assert result is ax
        assert destination.axes == [ax]
        assert original.axes == []
        assert ax.figure is destination
        assert ax.lines[0] is line
        np.testing.assert_array_equal(line.get_ydata(), [3, 4])
        assert ax.get_position().bounds == pytest.approx(position)
        assert plt.fignum_exists(original.number) is (not remove)
    finally:
        plt.close(original)
        plt.close(destination)
