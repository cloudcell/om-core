from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


class RecalcOverlay(QtWidgets.QWidget):
    """Modal overlay that blocks all interaction during recalculation."""

    cancel_requested = QtCore.Signal()  # Emitted when Esc is pressed

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        # Make it a native window to capture all events
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow)
        # Don't let mouse events pass through
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        # Take focus to capture keyboard events
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        # Semi-transparent dark tint to indicate frozen state
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.15);")


class RecalcWorker(QtCore.QObject):
    """Worker thread for running recalculation via session.execute without blocking GUI."""

    finished = QtCore.Signal(bool)  # success: True/False
    error = QtCore.Signal(str)

    def __init__(self, session: Any) -> None:
        super().__init__()
        self._session = session

    def run(self) -> None:
        """Run recalculation in background thread via session.execute."""
        try:
            self._session.execute("run_recalculation", scope="all")
            self.finished.emit(True)
        except KeyboardInterrupt:
            self.error.emit("Calculation cancelled")
        except Exception as e:
            self.error.emit(str(e))

    def request_cancel(self) -> None:
        """Request cancellation of the calculation."""
        try:
            self._session.execute("cancel_recalculation")
        except Exception:
            pass
