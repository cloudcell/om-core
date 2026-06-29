from __future__ import annotations

import os
import sys
from typing import Any


SPLASH_WIDTH = 480
SPLASH_HEIGHT = 320


def _splash_logo_path() -> str:
    """Return the filesystem path to the OM Core logo used on the splash screen."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets", "logo", "om-core-logo-transparent.png")


def render_splash(pixmap, progress: int = 0, message: str = "Loading...") -> None:
    """Paint the shared OM splash content onto a 480x320 QPixmap."""
    from PySide6 import QtGui, QtCore

    painter = QtGui.QPainter(pixmap)
    pixmap.fill(QtGui.QColor(245, 246, 247))

    # Draw the OM Core logo if available; otherwise fall back to text.
    logo_path = _splash_logo_path()
    logo_pixmap = QtGui.QPixmap(logo_path)
    if not logo_pixmap.isNull():
        target = QtCore.QRect(40, 65, 400, 110)
        scaled = logo_pixmap.scaled(
            target.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        x = target.x() + (target.width() - scaled.width()) // 2
        y = target.y() + (target.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
    else:
        font = QtGui.QFont()
        font.setPointSize(38)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(46, 134, 193))
        painter.drawText(QtCore.QRect(0, 75, 480, 50), QtCore.Qt.AlignmentFlag.AlignCenter, "OM Core")

    # Subtitle: bold, high-contrast black
    font = QtGui.QFont()
    font.setPointSize(16)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(0, 0, 0))
    painter.drawText(QtCore.QRect(0, 185, 480, 30), QtCore.Qt.AlignmentFlag.AlignCenter, "Open Modeling Environment")

    # Status message
    font.setPointSize(14)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(68, 68, 68))
    painter.drawText(QtCore.QRect(40, 225, 400, 30), QtCore.Qt.AlignmentFlag.AlignCenter, message)

    # Progress bar track
    painter.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200), 1))
    painter.setBrush(QtGui.QColor(230, 230, 230))
    painter.drawRoundedRect(40, 265, 400, 20, 4, 4)
    if progress > 0:
        fill_width = int(400 * progress / 100)
        painter.setPen(QtGui.QPen(QtGui.QColor(46, 134, 193), 1))
        painter.setBrush(QtGui.QColor(46, 134, 193))
        painter.drawRoundedRect(40, 265, fill_width, 20, 3, 3)

    # Progress percentage
    font.setPointSize(10)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(20, 20, 20))
    painter.drawText(QtCore.QRect(40, 265, 400, 20), QtCore.Qt.AlignmentFlag.AlignCenter, f"{progress}%")

    # Version label
    font.setPointSize(11)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(136, 136, 136))
    painter.drawText(QtCore.QRect(420, 295, 40, 20), QtCore.Qt.AlignmentFlag.AlignRight, "v1.0")

    painter.end()


class SplashScreen:
    """Fast, reliable splash window using a plain QWidget and a QLabel."""

    def __init__(self, app: Any, parent: Any = None) -> None:
        from PySide6 import QtWidgets, QtCore, QtGui

        self._app = app
        self._widget = QtWidgets.QWidget(
            parent,
            QtCore.Qt.WindowType.ToolTip
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint,
        )
        self._widget.setFixedSize(SPLASH_WIDTH, SPLASH_HEIGHT)
        self._label = QtWidgets.QLabel(self._widget)
        self._label.setGeometry(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)
        self._label.setScaledContents(True)

        self._pixmap = QtGui.QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
        self._pixmap.fill(QtCore.Qt.GlobalColor.white)
        self._label.setPixmap(self._pixmap)

    def move(self, x: int, y: int) -> None:
        self._widget.move(x, y)

    def show(self) -> None:
        from PySide6 import QtCore

        self._widget.winId()  # Force native window creation
        self._widget.show()
        self._app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def close(self) -> None:
        self._widget.close()

    def set_progress(self, value: int, message: str = "") -> None:
        from PySide6 import QtGui, QtCore

        new_pixmap = QtGui.QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
        render_splash(new_pixmap, value, message)
        self._label.setPixmap(new_pixmap)
        self._app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
