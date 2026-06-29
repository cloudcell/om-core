from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets, QtGui

from lib_gui.workspace_read_model import WorkspaceReadModel


def _load_icon(icon_name: str) -> QtGui.QIcon | None:
    """Load a Tabler SVG icon from the assets directory."""
    icon_path = Path(__file__).parent.parent / "assets" / "icons" / "tabler" / "icons" / "outline" / icon_name
    if icon_path.exists():
        return QtGui.QIcon(str(icon_path))
    return None


class _ModelBrowserTree(QtWidgets.QTreeWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_tag: str | None = None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
            print(f"DEBUG TREE KEY: key={key} hasFocus={self.hasFocus()}")
        super().keyPressEvent(event)

    def _root_tag_for_item(self, item: QtWidgets.QTreeWidgetItem | None) -> str | None:
        if item is None:
            return None
        root = item
        while root.parent() is not None:
            root = root.parent()
        data = root.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and data:
            return data[0]
        return None

    def startDrag(self, supportedActions: QtCore.Qt.DropActions) -> None:  # type: ignore[override]
        item = self.currentItem()
        tag: str | None = None
        if item is not None:
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and data:
                tag = data[0]
        self._drag_tag = tag
        if tag in {"root_dims", "root_cubes", "root_views"}:
            return
        super().startDrag(supportedActions)

    def _is_move_allowed(self, pos: QtCore.QPoint) -> bool:
        if not self._drag_tag:
            return True
        item = self.itemAt(pos)
        root_tag = self._root_tag_for_item(item)
        if self._drag_tag in {"dim", "dim_item"}:
            return root_tag == "root_dims"
        if self._drag_tag in {"cube", "cube_dim"}:
            return root_tag == "root_cubes"
        if self._drag_tag == "view":
            return root_tag == "root_views"
        if self._drag_tag in {"root_dims", "root_cubes", "root_views"}:
            return False
        return True

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self._is_move_allowed(pos):
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self._is_move_allowed(pos):
            event.ignore()
            return
        super().dropEvent(event)


class ModelBrowserDock(QtWidgets.QDockWidget):
    """Model browser dock widget showing workspace dimensions, cubes, and views.

    Uses WorkspaceReadModel for all metadata reads.
    """

    def __init__(
        self,
        *,
        session: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("Model Browser", parent)
        self._session = session
        self._workspace_read_model = WorkspaceReadModel(session)

        self._tree = _ModelBrowserTree(self)
        self._tree.setHeaderHidden(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAnimated(False)
        self._tree.setIndentation(16)
        self._tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        # Enable drag-and-drop for reordering of view nodes (left as-is)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)

        self.setWidget(self._tree)

        self.rebuild()

    @property
    def tree_widget(self) -> _ModelBrowserTree:
        return self._tree

    def focus_description(self) -> str:
        item = self._tree.currentItem()
        if item is None:
            return "Model Browser"
        parts: list[str] = []
        node = item
        while node is not None:
            parts.append(node.text(0))
            node = node.parent()
        return "Browse: " + " / ".join(reversed(parts))

    # -- helpers -----------------------------------------------------
    def _notify_workspace_changed(self) -> None:
        """Rebuild browser, ask main window to refresh views, rule panel, and mark workspace dirty."""
        self.rebuild()
        win = self.window()
        if hasattr(win, "_reload_active_view"):
            try:
                win._reload_active_view()
            except Exception:
                pass
        # Refresh rule panel after structural changes
        if hasattr(win, "_rule_panel") and win._rule_panel is not None:
            try:
                win._rule_panel.rebuild()
            except Exception:
                pass
        # Mark workspace as dirty after structural changes
        if hasattr(win, "_mark_dirty"):
            try:
                win._mark_dirty(True)
            except Exception:
                pass

    def _prune_outline_item(self, outline: list, item_id: str) -> list:
        """Remove any leaves for item_id from a Dimension.outline tree."""
        cleaned: list = []
        for n in outline:
            # Skip leaf nodes bound to the deleted item
            if getattr(n, "item_id", None) == item_id and not getattr(n, "children", None):
                continue
            children = getattr(n, "children", None)
            if isinstance(children, list) and children:
                n.children = self._prune_outline_item(children, item_id)
            cleaned.append(n)
        return cleaned

    # -- context menu ------------------------------------------------
    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return

        menu = QtWidgets.QMenu(self)
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        parent = item.parent()
        text = item.text(0)
        win = self.window()

        # Convenience: call MainWindow helper slots when available
        def _call_main(method: str, *args) -> bool:
            if hasattr(win, method):
                getattr(win, method)(*args)
                return True
            return False

        # Top-level roots -------------------------------------------------
        if parent is None:
            if text == "Dimensions":
                act_new_dim = menu.addAction("New Dimension…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_new_dim:
                    if not _call_main("_on_create_dimension"):
                        # Fallback: simple name dialog
                            # (no type selection here; default to set)
                        name, ok = QtWidgets.QInputDialog.getText(self, "New Dimension", "Name")
                        if ok and name.strip():
                            try:
                                if self._session is None:
                                    raise RuntimeError("No session available for create_dimension")
                                self._session.execute(
                                    "create_dimension",
                                    name=name.strip(),
                                    dim_type="set",
                                )
                                self._notify_workspace_changed()
                            except ValueError as e:
                                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                return
            if text == "Cubes":
                act_new_cube = menu.addAction("New Cube…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_new_cube:
                    _call_main("_on_create_cube")
                return
            if text == "Views":
                act_new_view = menu.addAction("New View…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_new_view:
                    _call_main("_on_add_view")
                return

        # Typed nodes ------------------------------------------------------
        if isinstance(data, tuple) and data:
            tag = data[0]
            payload = data[1:]

            # Dimension node under "Dimensions"
            if tag == "dim" and payload:
                dim_id = payload[0]
                dim = self._workspace_read_model.get_dimension(dim_id)
                if dim is None:
                    return
                dim_name = dim.get("name", "")
                act_add_item = menu.addAction(f"Add item to '{dim_name}'…")
                act_rename = menu.addAction(f"Rename dimension '{dim_name}'…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_add_item:
                    # Prefer MainWindow helper (preserves row_outline etc.)
                    if not _call_main("_on_add_item_to_dim", dim_id):
                        name, ok = QtWidgets.QInputDialog.getText(self, f"Add item to '{dim_name}'", "Item name")
                        if ok and name.strip():
                            if self._session is None:
                                raise RuntimeError("No session available for create_dimension_item")
                            self._session.execute(
                                "create_dimension_item",
                                dim_id=dim_id,
                                name=name.strip(),
                            )
                            self._notify_workspace_changed()
                elif chosen == act_rename:
                    new_name, ok = QtWidgets.QInputDialog.getText(
                        self,
                        "Rename Dimension",
                        "New name",
                        text=dim_name,
                    )
                    if ok:
                        new_name = new_name.strip()
                        if new_name and new_name != dim_name:
                            try:
                                if self._session is None:
                                    raise RuntimeError("No session available for rename_dimension")
                                self._session.execute(
                                    "rename_dimension",
                                    dim_id=dim_id,
                                    new_name=new_name,
                                )
                                self._notify_workspace_changed()
                            except (RuntimeError, ValueError) as e:
                                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                return

            # Dimension item node under a dimension
            if tag == "dim_item" and len(payload) >= 2:
                dim_id, item_id = payload[:2]
                dim = self._workspace_read_model.get_dimension(dim_id)
                if dim is None:
                    return
                items = dim.get("items", [])
                item_obj = next((it for it in items if it.get("id") == item_id), None)
                if item_obj is None:
                    return
                item_name = item_obj.get("name", "")
                act_rename = menu.addAction(f"Rename item '{item_name}'…")
                act_delete = menu.addAction(f"Delete item '{item_name}'…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_rename:
                    new_name, ok = QtWidgets.QInputDialog.getText(
                        self,
                        "Rename Item",
                        "New name",
                        text=item_name,
                    )
                    if ok:
                        new_name = new_name.strip()
                        if new_name and new_name != item_name:
                            if self._session is None:
                                raise RuntimeError("No session available for rename_dimension_item")
                            self._session.execute(
                                "rename_dimension_item",
                                dim_id=dim_id,
                                item_id=item_id,
                                new_name=new_name,
                            )
                            self._notify_workspace_changed()
                elif chosen == act_delete:
                    win = self.window()
                    if hasattr(win, "_confirm_and_delete_dimension_items"):
                        try:
                            deleted = bool(win._confirm_and_delete_dimension_items(dim_id, [item_id]))
                        except Exception:
                            deleted = False
                        if deleted:
                            self._notify_workspace_changed()
                return

            # Cube node under "Cubes"
            if tag == "cube" and payload:
                cube_id = payload[0]
                cube = self._workspace_read_model.get_cube(cube_id)
                if cube is None:
                    return
                cube_name = cube.get("name", "")
                act_rename = menu.addAction(f"Rename cube '{cube_name}'…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_rename:
                    new_name, ok = QtWidgets.QInputDialog.getText(
                        self,
                        "Rename Cube",
                        "New name",
                        text=cube_name,
                    )
                    if ok:
                        new_name = new_name.strip()
                        if new_name and new_name != cube_name:
                            if self._session is None:
                                raise RuntimeError("No session available for rename_cube")
                            self._session.execute(
                                "rename_cube",
                                cube_id=cube_id,
                                new_name=new_name,
                            )
                            self._notify_workspace_changed()
                return

            # Dimension attached under a cube (↳ Dim)
            if tag == "cube_dim" and len(payload) >= 2:
                cube_id, dim_id = payload[:2]
                cube = self._workspace_read_model.get_cube(cube_id)
                dim = self._workspace_read_model.get_dimension(dim_id)
                if cube is None or dim is None:
                    return
                dim_name = dim.get("name", "")
                cube_name = cube.get("name", "")
                act_remove = menu.addAction(f"Detach {dim_name} from {cube_name}")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_remove:
                    if self._session is None:
                        raise RuntimeError("No session available for detach_dimension_from_cube")
                    impact = self._session.query(
                        "cube_detach_impact", cube_id=cube_id, dim_id=dim_id
                    ) or {"data_cells": 0, "anchored_rules": 0, "rules": 0}
                    data_cells = impact.get("data_cells", 0)
                    anchored_rules = impact.get("anchored_rules", 0)
                    rules = impact.get("rules", 0)

                    if data_cells > 0 or anchored_rules > 0 or rules > 0:
                        msg = f"Detach dimension '{dim_name}' from cube '{cube_name}'?\n\n"
                        msg += f"This will permanently delete:\n"
                        msg += f"• {data_cells} data cell(s) (hard numbers)\n"
                        msg += f"• {anchored_rules} anchored rule(s)\n"
                        msg += f"• {rules} rule(s)\n\n"
                        msg += "This action cannot be undone."

                        resp = QtWidgets.QMessageBox.warning(
                            self,
                            "Confirm Detach Dimension",
                            msg,
                            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                            QtWidgets.QMessageBox.StandardButton.Cancel,
                        )
                        if resp != QtWidgets.QMessageBox.StandardButton.Yes:
                            return

                    self._session.execute(
                        "detach_dimension_from_cube",
                        cube_id=cube_id,
                        dim_id=dim_id,
                    )
                    self._notify_workspace_changed()
                return

            # View node under "Views"
            if tag == "view" and payload:
                view_id = payload[0]
                view = self._workspace_read_model.get_view(view_id)
                if view is None:
                    return
                view_name = view.get("name", "")
                act_rename = menu.addAction(f"Rename view '{view_name}'…")
                act_delete = menu.addAction(f"Delete view '{view_name}'…")
                chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
                if chosen == act_rename:
                    new_name, ok = QtWidgets.QInputDialog.getText(
                        self,
                        "Rename View",
                        "New name",
                        text=view_name,
                    )
                    if ok:
                        new_name = new_name.strip()
                        if new_name and new_name != view_name:
                            if self._session is None:
                                raise RuntimeError("No session available for view rename")
                            # Check for duplicate view names
                            existing_views = self._workspace_read_model.list_views()
                            if any(v.get("name") == new_name and v.get("id") != view_id for v in existing_views):
                                QtWidgets.QMessageBox.warning(
                                    self,
                                    "Rename View",
                                    f"A view named '{new_name}' already exists. Please choose a different name.",
                                )
                            else:
                                self._session.execute(
                                    "rename_view",
                                    view_id=view_id,
                                    new_name=new_name,
                                )
                                self._notify_workspace_changed()
                elif chosen == act_delete:
                    # Keep at least one view in the workspace.
                    if len(self._workspace_read_model.list_view_dtos(include_system=True)) <= 1:
                        QtWidgets.QMessageBox.information(
                            self,
                            "Delete View",
                            "Workspace must have at least one view.",
                        )
                        return
                    resp = QtWidgets.QMessageBox.question(
                        self,
                        "Delete View",
                        f"Delete view '{view_name}'?",
                    )
                    if resp == QtWidgets.QMessageBox.StandardButton.Yes:
                        if self._session is None:
                            raise RuntimeError("No session available for delete view")
                        self._session.execute(
                            "delete_view",
                            view_id=view_id,
                        )
                        self._notify_workspace_changed()
                return

    # -- tree rebuild -------------------------------------------------
    def rebuild(self) -> None:
        # Save expanded state and scroll position so tree does not collapse
        # or jump to top on every refresh.
        def _collect_expanded(item: QtWidgets.QTreeWidgetItem) -> set:
            expanded: set = set()
            if item.isExpanded():
                data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if data:
                    expanded.add(str(data))
            for i in range(item.childCount()):
                expanded.update(_collect_expanded(item.child(i)))
            return expanded

        old_expanded: set = set()
        for i in range(self._tree.topLevelItemCount()):
            old_expanded.update(_collect_expanded(self._tree.topLevelItem(i)))

        # Preserve scroll position (QTreeWidget scrolls to top after clear)
        vscroll = self._tree.verticalScrollBar().value() if self._tree.verticalScrollBar() else 0
        hscroll = self._tree.horizontalScrollBar().value() if self._tree.horizontalScrollBar() else 0

        self._tree.clear()

        # Load icons
        icon_dims = _load_icon("list-tree.svg")
        icon_cubes = _load_icon("cube.svg")
        icon_views = _load_icon("table.svg")
        icon_dim = _load_icon("list.svg")
        icon_cube = _load_icon("box.svg")
        icon_view = _load_icon("table.svg")

        # ---- Dimensions root and children ----
        root_dims = QtWidgets.QTreeWidgetItem(["Dimensions"])
        root_dims.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("root_dims", None))
        if icon_dims:
            root_dims.setIcon(0, icon_dims)
        for dim in self._workspace_read_model.list_dimension_dtos():
            is_seq = dim.get("dim_type", "set") == "seq"
            label = f"{dim['name']} 🔗" if is_seq else dim["name"]
            dim_item = QtWidgets.QTreeWidgetItem([label])
            dim_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("dim", dim["id"]))
            if icon_dim:
                dim_item.setIcon(0, icon_dim)
            for it in dim.get("items", []):
                item_node = QtWidgets.QTreeWidgetItem(dim_item, [it.get("name", "")])
                item_node.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("dim_item", dim["id"], it.get("id", "")))
            root_dims.addChild(dim_item)

        # ---- Cubes root and children ----
        root_cubes = QtWidgets.QTreeWidgetItem(["Cubes"])
        root_cubes.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("root_cubes", None))
        if icon_cubes:
            root_cubes.setIcon(0, icon_cubes)

        for cube in self._workspace_read_model.list_cube_dtos():
            cube_name = cube.get("name", "")
            cube_id = cube.get("id", "")
            dim_ids = cube.get("dimension_ids", [])
            cube_item = QtWidgets.QTreeWidgetItem(root_cubes, [cube_name])
            cube_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("cube", cube_id))
            if icon_cube:
                cube_item.setIcon(0, icon_cube)
            # Show attached dimensions under each cube
            for dim_id in dim_ids:
                dim = self._workspace_read_model.get_dimension(dim_id)
                if dim:
                    is_seq = dim.get("dim_type", "set") == "seq"
                    label = f"↳ {dim['name']} 🔗" if is_seq else f"↳ {dim['name']}"
                    dim_node = QtWidgets.QTreeWidgetItem(cube_item, [label])
                    dim_node.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("cube_dim", cube_id, dim["id"]))

        # ---- Views root and children ----
        root_views = QtWidgets.QTreeWidgetItem(["Views"])
        root_views.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("root_views", None))
        root_views.setFlags(root_views.flags() & ~QtCore.Qt.ItemFlag.ItemIsDropEnabled)
        if icon_views:
            root_views.setIcon(0, icon_views)

        for view in self._workspace_read_model.list_view_dtos():
            view_name = view.get("name", "")
            view_id = view.get("id", "")
            view_item = QtWidgets.QTreeWidgetItem(root_views, [view_name])
            view_item.setFlags(view_item.flags() | QtCore.Qt.ItemFlag.ItemIsDragEnabled)
            view_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("view", view_id))
            if icon_view:
                view_item.setIcon(0, icon_view)

        self._tree.addTopLevelItem(root_dims)
        self._tree.addTopLevelItem(root_cubes)
        self._tree.addTopLevelItem(root_views)

        root_dims.setExpanded(True)
        root_cubes.setExpanded(True)
        root_views.setExpanded(True)

        # Restore previously expanded child nodes
        def _restore_expanded(item: QtWidgets.QTreeWidgetItem) -> None:
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if data and str(data) in old_expanded:
                item.setExpanded(True)
            for i in range(item.childCount()):
                _restore_expanded(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _restore_expanded(self._tree.topLevelItem(i))

        # Restore scroll position so the tree doesn't jump to top
        if self._tree.verticalScrollBar():
            self._tree.verticalScrollBar().setValue(vscroll)
        if self._tree.horizontalScrollBar():
            self._tree.horizontalScrollBar().setValue(hscroll)
