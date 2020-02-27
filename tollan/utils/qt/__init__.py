#! /usr/bin/env python
from contextlib import contextmanager
import sys
import time
import signal
from PyQt5 import QtWidgets, QtCore


_app = None


class QThreadTarget(QtCore.QObject):

    finished = QtCore.pyqtSignal()

    should_keep_running = True

    def __init__(self, interval, target=lambda: None):
        super().__init__()
        self._interval = interval
        self._target = target

    @QtCore.pyqtSlot()
    def start(self):
        while self.should_keep_running:
            time.sleep(self._interval / 1e3)
            self._target()
        self.finished.emit()

    @QtCore.pyqtSlot()
    def stop(self):
        self.should_keep_running = False


def qt5app(args=None):
    if args and args[0] != sys.argv[0]:
        args = list(sys.argv[:1] + args)
    else:
        args = list()
    global _app
    _app = QtWidgets.QApplication.instance()
    if _app is None:
        _app = QtWidgets.QApplication(args)
    return _app


@contextmanager
def slot_disconnected(signal, slot):
    try:
        signal.disconnect(slot)
    except Exception:
        pass
    yield
    signal.connect(slot)


def setup_interrupt_handling():
    """Setup handling of KeyboardInterrupt (Ctrl-C) for PyQt5."""
    signal.signal(signal.SIGINT, _interrupt_handler)
    _safe_timer(50, lambda: None)


def _interrupt_handler(*args):
    """Handle KeyboardInterrupt: quit application."""
    QtWidgets.QApplication.quit()


def _safe_timer(timeout, func, *args, **kwargs):
    """
    Create a timer that is safe against garbage collection and overlapping
    calls. See: http://ralsina.me/weblog/posts/BB974.html
    """
    def timer_event():
        try:
            func(*args, **kwargs)
        finally:
            QtCore.QTimer.singleShot(timeout, timer_event)
    QtCore.QTimer.singleShot(timeout, timer_event)
