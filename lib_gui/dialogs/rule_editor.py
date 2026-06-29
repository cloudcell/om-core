from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class RuleEditorDialog(QtWidgets.QDialog):
    """Simple multiline rule editor with OK/Cancel."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, initial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Rule")
        self.setModal(True)

        self._edit = QtWidgets.QTextEdit(self)
        self._edit.setPlainText(initial)
        self._edit.setMinimumHeight(120)

        btn_ok = QtWidgets.QPushButton("OK", self)
        btn_cancel = QtWidgets.QPushButton("Cancel", self)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._edit)
        layout.addLayout(btns)

    @staticmethod
    def get_rule_body(parent: QtWidgets.QWidget | None, initial: str = "") -> tuple[str, bool]:
        dlg = RuleEditorDialog(parent, initial)
        ok = dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
        return dlg._edit.toPlainText(), ok
