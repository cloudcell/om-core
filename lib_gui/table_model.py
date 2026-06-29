from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui

from lib_utils.coerce import coerce_user_value
from lib_gui.cell_read_model import CellReadModel
from lib_gui.grid_read_model import GridReadModel


class CubeSliceTableModel(QtCore.QAbstractTableModel):
    def __init__(
        self,
        view_id: str,
        session: object,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._view_id = view_id
        self._session = session
        self._cell_read_model = CellReadModel(session)
        self._grid_read_model = GridReadModel(session)

    def rowCount(self, parent: QtCore.QModelIndex | None = None) -> int:  # noqa: N802
        return len(self._grid_read_model.row_keys(self._view_id))

    def columnCount(self, parent: QtCore.QModelIndex | None = None) -> int:  # noqa: N802
        return len(self._grid_read_model.col_keys(self._view_id))

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:  # noqa: N802
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == QtCore.Qt.Orientation.Horizontal:
            return self._grid_read_model.col_header(self._view_id, section)
        else:
            return self._grid_read_model.row_header(self._view_id, section)

        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return (
            QtCore.Qt.ItemFlag.ItemIsSelectable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsEditable
        )

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        row_keys = self._grid_read_model.row_keys(self._view_id)
        col_keys = self._grid_read_model.col_keys(self._view_id)
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(row_keys) or col < 0 or col >= len(col_keys):
            return None

        cell = self._cell_read_model.get_cell(self._view_id, row_keys[row], col_keys[col])

        if role == QtCore.Qt.ItemDataRole.BackgroundRole:
            source = cell.get("explain", {}).get("source")
            if source == "override":
                return QtGui.QBrush(QtGui.QColor("#ffff00"))
            return None

        if role not in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            return None

        value = cell.get("value")
        return "" if value is None else value

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if role != QtCore.Qt.ItemDataRole.EditRole or not index.isValid():
            return False

        if self._session is None:
            raise RuntimeError("No session available for set_cell_hardvalue")
        self._session.execute(
            "set_cell_hardvalue",
            view_id=self._view_id,
            cell_ref={
                "kind": "index",
                "value": {"row": index.row(), "col": index.column()},
            },
            value=coerce_user_value(value),
        )

        self.dataChanged.emit(index, index, [QtCore.Qt.ItemDataRole.DisplayRole])
        return True
