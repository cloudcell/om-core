from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from PySide6 import QtCore, QtGui

from lib_utils.coerce import coerce_user_value
from lib_gui.cell_read_model import CellReadModel
from lib_gui.grid_read_model import GridReadModel
from lib_gui.outline_read_model import OutlineReadModel


@dataclass
class _Node:
    label: str
    item_id: str | None = None  # row item id (leaf only)
    parent: "_Node | None" = None
    children: list["_Node"] = field(default_factory=list)

    def row(self) -> int:
        if self.parent is None:
            return 0
        try:
            return self.parent.children.index(self)
        except ValueError:
            return 0


class TreeSliceTableModel(QtCore.QAbstractItemModel):
    """Tree-table model:

    - Column 0 is the hierarchical row header (group / item names)
    - Columns 1..N are the pivoted data columns (e.g. Month)

    This is a prototype for pivot-table-style grouped line-items.
    """

    def __init__(
        self,
        view_id: str,
        row_dim_id: str,
        session: object,
        outline_read_model: OutlineReadModel,
        parent: QtCore.QObject | None = None,
        sep: str = "::",
        cell_read_model: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._view_id = view_id
        self._row_dim_id = row_dim_id
        self._sep = sep
        self._cell_read_model = cell_read_model or CellReadModel(session)
        self._session = session
        self._grid_read_model = GridReadModel(session)
        self._outline_read_model = outline_read_model

        self._root = _Node(label="__root__", item_id=None, parent=None)
        self._col_keys = self._grid_read_model.col_keys(self._view_id)
        self._build_tree()

    def node_for_index(self, index: QtCore.QModelIndex) -> _Node | None:
        if not index.isValid():
            return None
        n = index.internalPointer()
        return n if isinstance(n, _Node) else None

    # -----------------------------------------------------------------
    # Outline editing + persistence
    # -----------------------------------------------------------------

    def _persist_outline(self) -> None:
        """Phase 4: outline is read-only projection from graph. No-op."""
        pass

    def add_group(self, parent_index: QtCore.QModelIndex, name: str) -> None:
        parent_node = self._node_from_index(parent_index)
        if parent_node is None:
            parent_node = self._root

        insert_row = len(parent_node.children)
        self.beginInsertRows(parent_index if parent_index.isValid() else QtCore.QModelIndex(), insert_row, insert_row)
        parent_node.children.append(_Node(label=name, item_id=None, parent=parent_node))
        self.endInsertRows()
        self._persist_outline()

    def add_item_under(self, parent_index: QtCore.QModelIndex, name: str) -> None:
        """Create a new dimension item and place it under the given group (or root)."""
        view_dto = (
            self._session.query("view_detail", view_id=self._view_id)
            if self._session is not None
            else None
        )
        if not view_dto:
            return
        row_dim_ids = view_dto.get("row_dim_ids", [])
        if not row_dim_ids:
            return
        if row_dim_ids[0] != self._row_dim_id:
            return

        parent_node = self._node_from_index(parent_index)
        if parent_node is None:
            parent_node = self._root
        if parent_node.item_id is not None:
            parent_node = parent_node.parent or self._root

        if self._session is None:
            raise RuntimeError("No session available for create_dimension_item")
        result = self._session.execute(
            "create_dimension_item",
            dim_id=self._row_dim_id,
            name=name,
        )
        if not result.success:
            return
        item_name = name
        item_id = result.data.get("id") if result.data else None

        self.beginResetModel()
        if item_id:
            parent_node.children.append(_Node(label=item_name, item_id=item_id, parent=parent_node))
        self.endResetModel()
        self._persist_outline()

    def move_selected_to_group(self, group_index: QtCore.QModelIndex, item_indexes: list[QtCore.QModelIndex]) -> None:
        dest = self._node_from_index(group_index)
        if dest is None:
            dest = self._root
        if dest.item_id is not None:
            return

        nodes: list[_Node] = []
        for ix in item_indexes:
            n = self._node_from_index(ix)
            if n is None or n.item_id is None or n.parent is None:
                continue
            nodes.append(n)

        if not nodes:
            return

        self.beginResetModel()
        # Remove from old parents
        for n in nodes:
            if n.parent is not None and n in n.parent.children:
                n.parent.children.remove(n)
        # Append to dest
        for n in nodes:
            n.parent = dest
            dest.children.append(n)
        self.endResetModel()
        self._persist_outline()

    def move_selected_to_root(self, item_indexes: list[QtCore.QModelIndex]) -> None:
        nodes: list[_Node] = []
        for ix in item_indexes:
            n = self._node_from_index(ix)
            if n is None or n.item_id is None or n.parent is None:
                continue
            nodes.append(n)
        if not nodes:
            return

        self.beginResetModel()
        for n in nodes:
            if n.parent is not None and n in n.parent.children:
                n.parent.children.remove(n)
        for n in nodes:
            n.parent = self._root
            self._root.children.append(n)
        self.endResetModel()
        self._persist_outline()

    def rename_group(self, index: QtCore.QModelIndex, name: str) -> None:
        node = self._node_from_index(index)
        if node is None or node.item_id is not None:
            return
        node.label = name
        self.dataChanged.emit(index.siblingAtColumn(0), index.siblingAtColumn(0), [QtCore.Qt.ItemDataRole.DisplayRole])
        self._persist_outline()

    def delete_group(self, index: QtCore.QModelIndex) -> None:
        node = self._node_from_index(index)
        if node is None or node.parent is None or node.item_id is not None:
            return
        parent = node.parent
        row = node.row()

        # Promote children to parent (keeps items) then remove group.
        self.beginRemoveRows(self.parent(index), row, row)
        parent.children.pop(row)
        self.endRemoveRows()

        if node.children:
            insert_at = min(row, len(parent.children))
            self.beginInsertRows(self.parent(index), insert_at, insert_at + len(node.children) - 1)
            for i, ch in enumerate(node.children):
                ch.parent = parent
                parent.children.insert(insert_at + i, ch)
            self.endInsertRows()

        self._persist_outline()

    # -----------------------------------------------------------------
    # Drag/drop moving within outline
    # -----------------------------------------------------------------

    def supportedDropActions(self) -> QtCore.Qt.DropAction:  # noqa: N802
        return QtCore.Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return ["application/x-openm-outline-path"]

    def _path_for_node(self, node: _Node) -> list[int]:
        path: list[int] = []
        cur = node
        while cur.parent is not None and cur.parent is not self._root:
            path.append(cur.row())
            cur = cur.parent
        if cur.parent is self._root:
            path.append(cur.row())
        return list(reversed(path))

    def _node_for_path(self, path: list[int]) -> _Node | None:
        cur = self._root
        for r in path:
            if not (0 <= r < len(cur.children)):
                return None
            cur = cur.children[r]
        return cur

    def mimeData(self, indexes: list[QtCore.QModelIndex]) -> QtCore.QMimeData:  # noqa: N802
        md = QtCore.QMimeData()
        # Only support dragging one row at a time (column 0).
        idx0 = next((i for i in indexes if i.isValid() and i.column() == 0), None)
        if idx0 is None:
            return md
        node = self._node_from_index(idx0)
        if node is None or node.parent is None:
            return md
        payload = {"path": self._path_for_node(node)}
        md.setData("application/x-openm-outline-path", QtCore.QByteArray(json.dumps(payload).encode("utf-8")))
        return md

    def canDropMimeData(self, data: QtCore.QMimeData, action: QtCore.Qt.DropAction, row: int, column: int, parent: QtCore.QModelIndex) -> bool:  # noqa: N802
        if action != QtCore.Qt.DropAction.MoveAction:
            return False
        if not data.hasFormat("application/x-openm-outline-path"):
            return False
        return True

    def dropMimeData(self, data: QtCore.QMimeData, action: QtCore.Qt.DropAction, row: int, column: int, parent: QtCore.QModelIndex) -> bool:  # noqa: N802
        if not self.canDropMimeData(data, action, row, column, parent):
            return False

        raw = bytes(data.data("application/x-openm-outline-path")).decode("utf-8")
        try:
            payload = json.loads(raw)
            path = payload.get("path")
            if not isinstance(path, list) or not all(isinstance(x, int) for x in path):
                return False
        except Exception:
            return False

        node = self._node_for_path(path)
        if node is None or node.parent is None:
            return False

        def _is_ancestor(a: _Node, b: _Node) -> bool:
            cur = b.parent
            while cur is not None:
                if cur is a:
                    return True
                cur = cur.parent
            return False

        # Determine destination parent and insert row.
        drop_target = self._node_from_index(parent)
        if drop_target is None:
            dest_parent = self._root
            insert_row = row if row != -1 else len(dest_parent.children)
        elif drop_target.item_id is None:
            # Dropping on a group: append into it when row == -1
            dest_parent = drop_target
            insert_row = row if row != -1 else len(dest_parent.children)
        else:
            # Dropping on a leaf: treat as insert AFTER that leaf within its parent.
            dest_parent = drop_target.parent or self._root
            insert_row = (drop_target.row() + 1) if row == -1 else row

        insert_row = max(0, min(insert_row, len(dest_parent.children)))

        # Prevent cycles: can't drop a node into its own descendant.
        if dest_parent is node or _is_ancestor(node, dest_parent):
            return False

        src_parent = node.parent
        src_row = node.row()

        # No-op.
        if src_parent is dest_parent and (insert_row == src_row or insert_row == src_row + 1):
            return False

        # Remove first.
        self.beginRemoveRows(self._index_for_node(src_parent), src_row, src_row)
        src_parent.children.pop(src_row)
        self.endRemoveRows()

        # Adjust insert if moving within same parent and we removed an earlier row.
        if src_parent is dest_parent and insert_row > src_row:
            insert_row -= 1

        # Insert.
        self.beginInsertRows(self._index_for_node(dest_parent), insert_row, insert_row)
        node.parent = dest_parent
        dest_parent.children.insert(insert_row, node)
        self.endInsertRows()

        self._persist_outline()
        return True

    def _index_for_node(self, node: _Node) -> QtCore.QModelIndex:
        if node is self._root or node.parent is None:
            return QtCore.QModelIndex()
        return self.createIndex(node.row(), 0, node)

    # -----------------------------------------------------------------
    # Tree building
    # -----------------------------------------------------------------

    def _build_tree(self) -> None:
        outline: list[dict] = []
        by_id: dict[str, str] = {}

        # 1. Try view.row_outline via query
        row_tree = self._outline_read_model.row_outline_tree(self._view_id)
        nodes = row_tree.get("nodes", []) if row_tree else []
        if nodes:
            outline = nodes
        else:
            # 2. Try dim.outline via dimension_detail query
            dim_outline = self._outline_read_model.dimension_outline(self._row_dim_id)
            if dim_outline:
                outline = dim_outline

        # Build item name lookup from dimension_detail
        dim_dto = self._outline_read_model.dimension_detail(self._row_dim_id)
        if dim_dto:
            by_id = {it.get("id", ""): it.get("name", "") for it in dim_dto.get("items", [])}

        def _from_outline(parent: _Node, nodes: list[dict]) -> None:
            for raw in nodes:
                label = raw.get("label")
                item_id = raw.get("item_id")
                children = raw.get("children")
                if not isinstance(label, str):
                    continue
                if not isinstance(item_id, str):
                    item_id = None
                n = _Node(label=label, item_id=item_id, parent=parent)
                parent.children.append(n)
                if isinstance(children, list):
                    _from_outline(n, children)

        if outline:
            _from_outline(self._root, list(outline))
            # Any outline leaf with an item_id but empty label should display the item name.
            stack = [self._root]
            while stack:
                cur = stack.pop()
                for ch in cur.children:
                    if ch.item_id is not None and (ch.label == "" or ch.label is None):
                        ch.label = by_id.get(ch.item_id, ch.item_id)
                    stack.append(ch)
            return

        def _ensure_child(parent: _Node, label: str) -> _Node:
            for ch in parent.children:
                if ch.label == label and ch.item_id is None:
                    return ch
            n = _Node(label=label, parent=parent)
            parent.children.append(n)
            return n

        # Fallback flat list from dimension items via read model
        if dim_dto:
            items = dim_dto.get("items", [])
            for it in items:
                name = it.get("name", "")
                item_id = it.get("id", "")
                if not name or not item_id:
                    continue
                parts = [p.strip() for p in name.split(self._sep)]
                parts = [p for p in parts if p]
                if not parts:
                    parts = [name]
                cur = self._root
                for p in parts[:-1]:
                    cur = _ensure_child(cur, p)
                leaf = _Node(label=parts[-1], item_id=item_id, parent=cur)
                cur.children.append(leaf)

    # -----------------------------------------------------------------
    # Helpers for MainWindow integration
    # -----------------------------------------------------------------

    def row_key_for_index(self, index: QtCore.QModelIndex) -> tuple[str, ...] | None:
        node = self._node_from_index(index)
        if node is None or node.item_id is None:
            return None
        return (node.item_id,)

    def col_key_for_column(self, column: int) -> tuple[str, ...] | None:
        # column 0 is label
        if column <= 0:
            return None
        c = column - 1
        if 0 <= c < len(self._col_keys):
            return self._col_keys[c]
        return None

    # -----------------------------------------------------------------
    # Qt model implementation
    # -----------------------------------------------------------------

    def _node_from_index(self, index: QtCore.QModelIndex) -> _Node | None:
        if not index.isValid():
            return self._root
        n = index.internalPointer()
        return n if isinstance(n, _Node) else None

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:  # noqa: N802
        parent_node = self._node_from_index(parent)
        if parent_node is None:
            return QtCore.QModelIndex()
        if not (0 <= row < len(parent_node.children)):
            return QtCore.QModelIndex()
        child = parent_node.children[row]
        return self.createIndex(row, column, child)

    def parent(self, index: QtCore.QModelIndex) -> QtCore.QModelIndex:  # noqa: N802
        node = self._node_from_index(index)
        if node is None or node.parent is None or node.parent is self._root:
            return QtCore.QModelIndex()
        return self.createIndex(node.parent.row(), 0, node.parent)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        node = self._node_from_index(parent)
        if node is None:
            return 0
        return len(node.children)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        return 1 + len(self._col_keys)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            if section == 0:
                dim_dto = self._outline_read_model.dimension_detail(self._row_dim_id)
                return dim_dto.get("name", "") if dim_dto else ""
            return self._grid_read_model.col_header(self._view_id, section - 1)
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags

        node = self._node_from_index(index)
        if node is None:
            return QtCore.Qt.ItemFlag.NoItemFlags

        base = QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        if index.column() > 0 and node.item_id is not None:
            base |= QtCore.Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        node = self._node_from_index(index)
        if node is None:
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return node.label
            if node.item_id is None:
                return ""
            row_key = (node.item_id,)
            col_key = self._col_keys[index.column() - 1]
            cell_dto = self._cell_read_model.get_cell(self._view_id, row_key, col_key)
            value = cell_dto.get("value")
            return "" if value is None else value

        if role == QtCore.Qt.ItemDataRole.BackgroundRole:
            if index.column() == 0 or node.item_id is None:
                return None
            row_key = (node.item_id,)
            col_key = self._col_keys[index.column() - 1]
            cell_dto = self._cell_read_model.get_cell(self._view_id, row_key, col_key)
            source = cell_dto.get("explain", {}).get("source")
            if source == "override":
                return QtGui.QBrush(QtGui.QColor("#ffff00"))
            return None

        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if role != QtCore.Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        node = self._node_from_index(index)
        if node is None or node.item_id is None or index.column() <= 0:
            return False

        row_key = (node.item_id,)
        col_key = self._col_keys[index.column() - 1]
        if self._session is None:
            raise RuntimeError("No session available for set_cell_hardvalue")
        self._session.execute(
            "set_cell_hardvalue",
            view_id=self._view_id,
            cell_ref={
                "kind": "keys",
                "value": {"row_key": list(row_key), "col_key": list(col_key)},
            },
            value=coerce_user_value(value),
        )
        self.dataChanged.emit(index, index, [QtCore.Qt.ItemDataRole.DisplayRole])
        return True
