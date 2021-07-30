#! /usr/bin/env python

"""Some matplotlib helpers."""

from .log import get_logger
import sys
from pathlib import Path
from PyQt5 import QtWidgets
import matplotlib

matplotlib.use('Qt5Agg')  # noqa

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_qt5agg import \
    FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qt5agg import \
    NavigationToolbar2QT as NavigationToolbar  # noqa: E402


from .qt import qt5app  # noqa: E402


__all__ = ['save_or_show', 'make_tabular_legend']


class ScrollableMplWindow(QtWidgets.QMainWindow):
    def __init__(self, fig):
        super().__init__()
        _widget = QtWidgets.QWidget()
        self.setCentralWidget(_widget)
        layout = QtWidgets.QVBoxLayout(_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        canvas = FigureCanvas(fig)
        self.addToolBar(NavigationToolbar(canvas, self))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(canvas)
        self._fig_dpi = canvas.geometry().width() / \
            fig.get_size_inches()[0]
        layout.addWidget(scroll)

    @classmethod
    def show_standalone(cls, fig, size=None, padding=(10, 10)):
        app = qt5app()
        win = cls(fig)
        app._win = win
        win.show()
        dpi = win._fig_dpi
        if size is not None:
            w, h = size
            win.resize(w * dpi + padding[0], h * dpi + padding[1])
        app.exec_()


def save_or_show(fig, filepath,
                 bbox_inches='tight',
                 window_type='default',
                 save=None,
                 **kwargs):
    '''Save figure or show  plot, depending on
    the last sys.argv'''
    logger = get_logger()
    argv = sys.argv[1:]
    if save is None:
        if not argv:
            save = False
        else:
            try:
                s = int(argv[-1])
                save = True if s == 1 else False
            except ValueError:
                if argv[-1].lower() in ['true', 'save']:
                    save = True
                elif argv[-1].lower() in ['plot', ]:
                    save = False
                else:
                    save = False
    if save:
        fig.savefig(
            filepath,
            dpi='figure',
            format=Path(filepath).suffix.lstrip('.'), **kwargs)
        logger.info('figure saved: {0}'.format(filepath))
        plt.close()
    else:
        if window_type == 'default':
            plt.show()
        elif window_type == 'scrollable':
            ScrollableMplWindow.show_standalone(fig, **kwargs)
        else:
            raise NotImplementedError


def make_tabular_legend(
        ax, handles, *cols,
        colnames=None, colwidths=5, **kwargs):
    if set([len(handles)]) != set(map(len, cols)):
        raise ValueError("all columns need to have the same size")

    if colnames is not None and len(colnames) != len(cols):
        raise ValueError("size of colnames need to match that of the cols")
    if isinstance(colwidths, int):
        colwidths = [colwidths] * len(handles)

    dummy_patch = matplotlib.patches.Rectangle(
            (1, 1), 1, 1,
            fill=False, edgecolor='none', visible=False)
    handles = [dummy_patch, ] + list(handles)
    labels = []
    if colnames is not None:
        label_row = []
        for colwidth, colname in zip(colwidths, colnames):
            if isinstance(colname, tuple):
                name, width = colname
            else:
                name = colname
                width = len(colname)
            print(name, width, colwidth)
            label_row.append(' ' * int(width) + name)
        labels.append(' '.join(label_row))
    for i, row in enumerate(zip(*cols)):
        label_row = []
        for j, value in enumerate(row):
            fmt = f'{{:>{colwidths[j]}s}}'
            label_row.append(fmt.format(str(value)))
        labels.append(' '.join(label_row))

    return ax.legend(handles, labels, **kwargs)
