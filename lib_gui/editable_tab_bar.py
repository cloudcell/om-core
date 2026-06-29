from __future__ import annotations

import logging

from PySide6 import QtCore, QtGui, QtWidgets


class EditableTabBar(QtWidgets.QTabBar):
    """Tab bar that supports inline editing of tab labels via double-click."""

    tab_renamed = QtCore.Signal(int, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor: QtWidgets.QLineEdit | None = None
        self._editing_index: int = -1
        self._committing: bool = False
        logging.debug("DEBUG EditableTabBar: created, isMovable=%s", self.isMovable())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        logging.debug("DEBUG mousePressEvent: button=%s, pos=%s, isMovable=%s", event.button(), event.pos(), self.isMovable())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        logging.debug("DEBUG mouseMoveEvent: buttons=%s, pos=%s", event.buttons(), event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        logging.debug("DEBUG mouseReleaseEvent: button=%s, pos=%s", event.button(), event.pos())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            index = self.tabAt(event.pos())
            if index >= 0:
                self._start_editing(index)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _start_editing(self, index: int) -> None:
        if self._editor is not None:
            self._commit_edit()

        self._editing_index = index
        rect = self.tabRect(index)
        
        self._editor = QtWidgets.QLineEdit(self)
        self._editor.setText(self.tabText(index))
        self._editor.setGeometry(rect)
        self._editor.selectAll()
        self._editor.setFocus()
        self._editor.show()
        
        self._editor.editingFinished.connect(self._commit_edit)
        self._editor.returnPressed.connect(self._commit_edit)
        self._editor.installEventFilter(self)

    def _commit_edit(self) -> None:
        if self._editor is None or self._editing_index < 0:
            return
        
        # Prevent reentrant calls
        if self._committing:
            return
        self._committing = True

        new_name = self._editor.text().strip()
        old_name = self.tabText(self._editing_index)
        
        # Disconnect signals to prevent multiple calls
        try:
            self._editor.editingFinished.disconnect(self._commit_edit)
        except (TypeError, RuntimeError):
            pass
        try:
            self._editor.returnPressed.disconnect(self._commit_edit)
        except (TypeError, RuntimeError):
            pass
        
        self._editor.deleteLater()
        self._editor = None
        index = self._editing_index
        self._editing_index = -1
        self._committing = False

        if new_name and new_name != old_name:
            self.setTabText(index, new_name)
            self.tab_renamed.emit(index, new_name)

    def _cancel_edit(self) -> None:
        if self._editor is not None:
            self._editor.deleteLater()
            self._editor = None
            self._editing_index = -1

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj == self._editor and event.type() == QtCore.QEvent.Type.KeyPress:
            key_event = event
            if isinstance(key_event, QtGui.QKeyEvent):
                if key_event.key() == QtCore.Qt.Key.Key_Escape:
                    self._cancel_edit()
                    return True
        return super().eventFilter(obj, event)
