"""Info Toolbox - Display information about selected model elements."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from lib_gui.workspace_read_model import WorkspaceReadModel


class InfoToolboxDock(QtWidgets.QDockWidget):
    """Dock widget displaying detailed info about selected model elements."""

    def __init__(
        self,
        *,
        cell_read_model: object,
        workspace_read_model: WorkspaceReadModel,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("Info Toolbox", parent)
        self._cell_read_model = cell_read_model
        self._workspace_read_model = workspace_read_model

        # Main widget with layout
        self._widget = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header label showing current selection type
        self._header_label = QtWidgets.QLabel("Select a model element")
        self._header_label.setStyleSheet(
            "font-weight: bold; font-size: 12px; color: #333;"
        )
        layout.addWidget(self._header_label)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #ccc;")
        layout.addWidget(line)

        # Content area with property labels
        self._content_layout = QtWidgets.QFormLayout()
        self._content_layout.setSpacing(6)
        self._content_layout.setLabelAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        
        # Property labels
        self._prop_labels: dict[str, QtWidgets.QLabel] = {}
        self._add_property_row("Type", "—")
        self._add_property_row("ID", "—")
        self._add_property_row("Name", "—")
        self._add_property_row("Details", "—")
        
        # Cube section properties (no header/separator)
        self._cube_prop_labels: dict[str, QtWidgets.QLabel] = {}
        self._add_cube_property_row("Cube ID", "—")
        self._add_cube_property_row("Rules", "—")
        self._add_cube_property_row("Hardnumbers", "—")

        self._cell_prop_labels: dict[str, QtWidgets.QLabel] = {}
        self._add_cell_property_row("Address", "—")
        self._add_cell_property_row("Value", "—")
        self._add_cell_property_row("Source", "—")
        self._add_cell_property_row("Rule", "—")
        self._add_cell_property_row("Rules", "—")
        self._add_cell_property_row("Override", "—")

        # Cell section separator and header (hidden by default, shown for cells)
        self._cell_section_separator = QtWidgets.QFrame()
        self._cell_section_separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self._cell_section_separator.setStyleSheet("background-color: #ccc;")
        self._cell_section_separator.setVisible(False)
        layout.addWidget(self._cell_section_separator)

        self._cell_section_header = QtWidgets.QLabel("Cell Properties")
        self._cell_section_header.setStyleSheet("font-weight: bold; font-size: 11px; color: #666;")
        self._cell_section_header.setVisible(False)
        layout.addWidget(self._cell_section_header)

        layout.addLayout(self._content_layout)
        layout.addStretch(1)

        self.setWidget(self._widget)
        self._current_element: tuple[str, str] | None = None

    def _add_property_row(self, label: str, default: str) -> None:
        """Add a property row to the content layout."""
        label_widget = QtWidgets.QLabel(f"{label}:")
        label_widget.setStyleSheet("font-weight: 500; color: #555;")
        
        # Use scrollable text edit for Details field (can explode with long content)
        if label.lower() == "details":
            value_widget = QtWidgets.QTextEdit(default)
            value_widget.setReadOnly(True)
            value_widget.setMaximumHeight(100)
            value_widget.setStyleSheet("color: #333; background: transparent; border: none;")
            value_widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            value_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            value_widget = QtWidgets.QLabel(default)
            value_widget.setStyleSheet("color: #333;")
            value_widget.setWordWrap(True)
        self._content_layout.addRow(label_widget, value_widget)
        self._prop_labels[label.lower()] = value_widget

    def _add_cell_property_row(self, label: str, default: str) -> None:
        """Add a cell property row to the content layout."""
        label_widget = QtWidgets.QLabel(f"{label}:")
        label_widget.setStyleSheet("font-weight: 500; color: #555;")
        label_widget.setVisible(False)
        
        # Use scrollable text edit for Value field (can explode with long rules/text)
        if label.lower() == "value":
            value_widget = QtWidgets.QTextEdit(default)
            value_widget.setReadOnly(True)
            value_widget.setMaximumHeight(80)
            value_widget.setStyleSheet("color: #333; background: transparent; border: none;")
            value_widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            value_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            value_widget = QtWidgets.QLabel(default)
            value_widget.setStyleSheet("color: #333;")
            value_widget.setWordWrap(True)
        value_widget.setVisible(False)
        self._content_layout.addRow(label_widget, value_widget)
        self._cell_prop_labels[label.lower()] = (label_widget, value_widget)

    def _add_cube_property_row(self, label: str, default: str) -> None:
        """Add a cube property row to the content layout."""
        label_widget = QtWidgets.QLabel(f"{label}:")
        label_widget.setStyleSheet("font-weight: 500; color: #555;")
        label_widget.setVisible(False)

        value_widget = QtWidgets.QLabel(default)
        value_widget.setStyleSheet("color: #333;")
        value_widget.setWordWrap(True)
        value_widget.setVisible(False)
        self._content_layout.addRow(label_widget, value_widget)
        self._cube_prop_labels[label.lower()] = (label_widget, value_widget)

    def clear(self) -> None:
        """Clear the info display."""
        self._header_label.setText("Select a model element")
        self._prop_labels["type"].setText("—")
        self._prop_labels["id"].setText("—")
        self._prop_labels["name"].setText("—")
        self._prop_labels["details"].setPlainText("—")
        self._current_element = None
        # Hide cube section
        for label_widget, value_widget in self._cube_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)
        # Hide cell metadata section
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_dimension(self, dim_id: str) -> None:
        """Display info about a dimension."""
        dim = (
            self._workspace_read_model.get_dimension(dim_id)
            if self._workspace_read_model is not None
            else None
        )
        if dim is None:
            self.clear()
            return

        self._header_label.setText("Dimension")
        self._prop_labels["type"].setText(f"Dimension ({dim.get('dim_type', 'set')})")
        self._prop_labels["id"].setText(dim.get("id", ""))
        self._prop_labels["name"].setText(dim.get("name", ""))

        items = dim.get("items", [])
        item_count = len(items)
        items_str = f"{item_count} items"
        if items:
            items_preview = ", ".join(it.get("name", "") for it in items[:5])
            if item_count > 5:
                items_preview += f", ... ({item_count - 5} more)"
            items_str += f"\n{items_preview}"

        self._prop_labels["details"].setPlainText(items_str)
        self._current_element = ("dim", dim_id)
        self._widget.update()
        # Hide cell metadata when showing dimension
        self._cell_section_separator.setVisible(False)
        self._cell_section_header.setVisible(False)
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_dimension_item(self, dim_id: str, item_id: str) -> None:
        """Display info about a dimension item."""
        dim = (
            self._workspace_read_model.get_dimension(dim_id)
            if self._workspace_read_model is not None
            else None
        )
        if dim is None:
            self.clear()
            return

        items = dim.get("items", [])
        item = next((it for it in items if it.get("id") == item_id), None)
        if item is None:
            self.clear()
            return

        self._header_label.setText("Dimension Item")
        self._prop_labels["type"].setText("Item")
        self._prop_labels["id"].setText(item.get("id", ""))
        self._prop_labels["name"].setText(item.get("name", ""))

        idx = next((i for i, it in enumerate(items) if it.get("id") == item_id), -1)
        self._prop_labels["details"].setPlainText(
            f"Parent dimension: {dim.get('name', '')}\n"
            f"Index: {idx + 1} of {len(items)}"
        )
        self._current_element = ("dim_item", f"{dim_id}:{item_id}")
        self._widget.update()
        # Hide cell metadata when showing dimension item (safely check if attributes exist)
        sep = getattr(self, "_cell_section_separator", None)
        if sep:
            sep.setVisible(False)
        header = getattr(self, "_cell_section_header", None)
        if header:
            header.setVisible(False)
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_cube(self, cube_id: str) -> None:
        """Display info about a cube."""
        cube = self._workspace_read_model.get_cube(cube_id)
        if cube is None:
            self.clear()
            return
        cube_name = cube.get("name", "")
        cube_id_str = cube.get("id", "")
        dim_ids = cube.get("dimension_ids", [])
        override_count = cube.get("user_override_count", 0)

        self._header_label.setText("Cube")
        self._prop_labels["type"].setText("Cube")
        self._prop_labels["id"].setText(cube_id_str)
        self._prop_labels["name"].setText(cube_name)

        dims_str = f"{len(dim_ids)} dimensions"
        if dim_ids:
            dims = []
            for did in dim_ids:
                d = self._workspace_read_model.get_dimension(did)
                if d:
                    dims.append(d.get("name", ""))
                else:
                    dims.append(did[:8] + "...")
            dims_str += f"\n{', '.join(dims)}"

        self._prop_labels["details"].setPlainText(
            f"{dims_str}\n"
            f"User overrides: {override_count}"
        )
        self._current_element = ("cube", cube_id)
        self._widget.update()
        # Hide cell metadata when showing cube
        self._cell_section_separator.setVisible(False)
        self._cell_section_header.setVisible(False)
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_cube_dimension(self, cube_id: str, dim_id: str) -> None:
        """Display info about a dimension attached to a cube."""
        cube = self._workspace_read_model.get_cube(cube_id)
        dim = self._workspace_read_model.get_dimension(dim_id)
        if cube is None or dim is None:
            self.clear()
            return

        self._header_label.setText("Cube Dimension")
        self._prop_labels["type"].setText(f"Dimension ({dim.get('dim_type', 'set')})")
        self._prop_labels["id"].setText(dim.get("id", ""))
        self._prop_labels["name"].setText(f"↳ {dim.get('name', '')}")
        self._prop_labels["details"].setPlainText(
            f"Attached to cube: {cube.get('name', '')}\n"
            f"Items: {dim.get('item_count', 0)}"
        )
        self._current_element = ("cube_dim", f"{cube_id}:{dim_id}")
        self._widget.update()
        # Hide cell metadata when showing cube dimension
        self._cell_section_separator.setVisible(False)
        self._cell_section_header.setVisible(False)
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_view(self, view_id: str) -> None:
        """Display info about a view."""
        view = self._workspace_read_model.get_view(view_id)
        if view is None:
            self.clear()
            return

        self._header_label.setText("View")
        self._prop_labels["type"].setText("Table View")
        self._prop_labels["id"].setText(view.get("id", ""))
        self._prop_labels["name"].setText(view.get("name", ""))

        row_dim_ids = view.get("row_dim_ids", [])
        col_dim_ids = view.get("col_dim_ids", [])
        page_dim_ids = view.get("page_dim_ids", [])

        row_str = f"Rows: {len(row_dim_ids)} dim(s)"
        if row_dim_ids:
            d = self._workspace_read_model.get_dimension(row_dim_ids[0])
            if d:
                row_str += f" ({d.get('name', '')})"

        col_str = f"Cols: {len(col_dim_ids)} dim(s)"
        if col_dim_ids:
            d = self._workspace_read_model.get_dimension(col_dim_ids[0])
            if d:
                col_str += f" ({d.get('name', '')})"

        page_str = ""
        if page_dim_ids:
            page_str = f"\nPage dims: {len(page_dim_ids)}"

        cube_id = view.get("cube_id", "")
        self._prop_labels["details"].setPlainText(
            f"Cube: {cube_id[:8]}...\n"
            f"{row_str}\n{col_str}{page_str}"
        )
        self._current_element = ("view", view_id)
        self._widget.update()
        # Hide cell metadata when showing view
        self._cell_section_separator.setVisible(False)
        self._cell_section_header.setVisible(False)
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(False)
            value_widget.setVisible(False)

    def show_cell(
        self,
        view_id: str,
        row_key: tuple[str, ...],
        col_key: tuple[str, ...],
    ) -> None:
        """Display info about a cell in the grid."""
        view = self._workspace_read_model.get_view(view_id)
        if view is None:
            self.clear()
            return
        cube_id = view.get("cube_id", "")
        if not cube_id:
            self.clear()
            return
        cube = self._workspace_read_model.get_cube(cube_id)
        if cube is None:
            self.clear()
            return

        # Phase D: Use CellReadModel for cell reads and address resolution
        cell_dto = self._cell_read_model.get_cell(view_id, row_key, col_key)
        addr_dto = self._cell_read_model.addr_for_view_keys(view_id, row_key, col_key)
        full_addr = addr_dto
        source = cell_dto.get("explain", {}).get("source", "empty")
        cell_value = cell_dto.get("value")
        cell_rule_text = self._cell_read_model.cell_rule(cube_id, full_addr) or "None"
        rules_text = self._cell_read_model.rule_detail(cube_id, full_addr) or "None"
        counts = self._cell_read_model.cube_rule_counts(cube_id)
        cell_rule_count = counts["cell_rules"]
        rule_count = counts["rules"]

        addr_str = "(" + ", ".join(full_addr) + ")"

        # Determine source and override status
        is_override = source == "override"

        hardnumber_count = cube.get("user_override_count", 0)

        # Update main properties
        self._header_label.setText("Cell")
        self._prop_labels["type"].setText("Data Cell")
        self._prop_labels["id"].setText(f"{row_key} × {col_key}")
        self._prop_labels["name"].setText(f"Cube: {cube.get('name', '')}")
        self._prop_labels["details"].setPlainText(
            f"Value: {cell_value}\n"
            f"Source: {source}"
        )

        # Show and update cube section
        for label_widget, value_widget in self._cube_prop_labels.values():
            label_widget.setVisible(True)
            value_widget.setVisible(True)

        self._cube_prop_labels["cube id"][1].setText(cube_id)
        self._cube_prop_labels["rules"][1].setText(str(rule_count))
        self._cube_prop_labels["hardnumbers"][1].setText(str(hardnumber_count))

        # Show and update cell metadata section
        for label_widget, value_widget in self._cell_prop_labels.values():
            label_widget.setVisible(True)
            value_widget.setVisible(True)

        self._cell_prop_labels["address"][1].setText(addr_str)
        self._cell_prop_labels["value"][1].setPlainText(str(cell_value) if cell_value is not None else "—")
        self._cell_prop_labels["source"][1].setText(source)
        self._cell_prop_labels["rule"][1].setText(cell_rule_text)
        self._cell_prop_labels["rules"][1].setText(rules_text)
        self._cell_prop_labels["override"][1].setText(
            "Yes (User Hardcoded)" if is_override else "No (Rule)"
        )
        
        self._current_element = ("cell", f"{view_id}:{row_key}:{col_key}")
        self._widget.update()
