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
    result_ready = QtCore.Signal(dict)  # full command result data

    def __init__(self, session: Any, scope: str = "all") -> None:
        super().__init__()
        self._session = session
        self._scope = scope

    def run(self) -> None:
        """Run recalculation in background thread via session.execute."""
        try:
            result = self._session.execute("run_recalculation", scope=self._scope)
            if result.success:
                data = result.data or {}
                self.result_ready.emit(data)
                self.finished.emit(True)
            else:
                self.error.emit(result.error or "Recalculation failed")
                self.finished.emit(False)
        except KeyboardInterrupt:
            self.error.emit("Calculation cancelled")
            self.finished.emit(False)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)

    def request_cancel(self) -> None:
        """Request cancellation of the calculation."""
        try:
            self._session.execute("cancel_recalculation")
        except Exception:
            pass
