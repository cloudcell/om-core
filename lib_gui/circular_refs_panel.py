from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

class CircularReferencesPanel(QtWidgets.QWidget):
    """Dedicated panel for circular reference analysis and navigation."""

    navigate_requested = QtCore.Signal(str, tuple)
    open_trace_requested = QtCore.Signal(str, tuple)

    def __init__(
        self,
        *,
        session=None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._active_cube_id: str | None = None
        self._focus_cube_id: str | None = None
        self._focus_addr: tuple[str, ...] | None = None

        self._analysis: dict[str, Any] = {}
        self._cycle_nodes: list[dict[str, Any]] = []
        self._active_cycle_index = 0
        self._active_node_index = 0

        self._title = QtWidgets.QLabel("Circular References", self)
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)

        self._depth = QtWidgets.QSpinBox(self)
        self._depth.setRange(2, 100)
        self._depth.setValue(12)
        self._depth.setPrefix("Depth ")
        self._depth.valueChanged.connect(self.rebuild)

        self._btn_refresh = QtWidgets.QToolButton(self)
        self._btn_refresh.setText("Refresh")
        self._btn_refresh.clicked.connect(self.rebuild)

        top_controls = QtWidgets.QHBoxLayout()
        top_controls.setContentsMargins(0, 0, 0, 0)
        top_controls.addWidget(self._title)
        top_controls.addStretch(1)
        top_controls.addWidget(self._depth)
        top_controls.addWidget(self._btn_refresh)

        self._summary = QtWidgets.QLabel("Select a data cell to inspect circular paths.", self)
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("color: #2f3b52;")

        self._cycle_picker = QtWidgets.QComboBox(self)
        self._cycle_picker.currentIndexChanged.connect(self._on_cycle_changed)

        self._cycle_meta = QtWidgets.QLabel("Cycle 0 of 0", self)
        self._cycle_meta.setStyleSheet("color: #4d5b73;")

        picker_row = QtWidgets.QHBoxLayout()
        picker_row.setContentsMargins(0, 0, 0, 0)
        picker_row.setSpacing(8)
        picker_row.addWidget(QtWidgets.QLabel("Cycle", self))
        picker_row.addWidget(self._cycle_picker, 1)
        picker_row.addWidget(self._cycle_meta)

        self._path = QtWidgets.QPlainTextEdit(self)
        self._path.setReadOnly(True)
        self._path.setPlaceholderText("Circular path will appear here")
        self._path.setMaximumBlockCount(4)

        self._nodes = QtWidgets.QListWidget(self)
        self._nodes.itemActivated.connect(self._on_node_activated)
        self._nodes.currentRowChanged.connect(self._on_node_row_changed)

        self._btn_prev = QtWidgets.QToolButton(self)
        self._btn_prev.setText("Previous")
        self._btn_prev.clicked.connect(self._on_prev_node)

        self._btn_next = QtWidgets.QToolButton(self)
        self._btn_next.setText("Next")
        self._btn_next.clicked.connect(self._on_next_node)

        self._btn_copy = QtWidgets.QToolButton(self)
        self._btn_copy.setText("Copy cycle path")
        self._btn_copy.clicked.connect(self._copy_cycle_path)

        self._btn_open_trace = QtWidgets.QToolButton(self)
        self._btn_open_trace.setText("Open all nodes in Calculation Flow")
        self._btn_open_trace.clicked.connect(self._open_in_flow)

        self._btn_focus_editable = QtWidgets.QToolButton(self)
        self._btn_focus_editable.setText("Focus first editable rule")
        self._btn_focus_editable.clicked.connect(self._focus_first_editable)

        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self._btn_prev)
        actions.addWidget(self._btn_next)
        actions.addWidget(self._btn_copy)
        actions.addWidget(self._btn_open_trace)
        actions.addWidget(self._btn_focus_editable)
        actions.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(top_controls)
        layout.addWidget(self._summary)
        layout.addLayout(picker_row)
        layout.addWidget(self._path)
        layout.addWidget(self._nodes, 1)
        layout.addLayout(actions)

        QtGui.QShortcut(QtGui.QKeySequence("Alt+Up"), self, activated=self._on_prev_node)
        QtGui.QShortcut(QtGui.QKeySequence("Alt+Down"), self, activated=self._on_next_node)

    def set_active_cube(self, cube_id: str | None) -> None:
        if cube_id != self._active_cube_id and self._focus_cube_id is not None and self._focus_cube_id != cube_id:
            self._focus_cube_id = None
            self._focus_addr = None
        self._active_cube_id = cube_id
        self.rebuild()

    def set_focus_cell(self, cube_id: str | None, addr: tuple[str, ...] | None) -> None:
        self._focus_cube_id = cube_id
        self._focus_addr = addr
        self.rebuild()

    def rebuild(self) -> None:
        self._analysis = {}
        self._cycle_nodes = []
        self._active_cycle_index = 0
        self._active_node_index = 0

        self._cycle_picker.blockSignals(True)
        self._cycle_picker.clear()
        self._cycle_picker.blockSignals(False)
        self._path.setPlainText("")
        self._nodes.clear()

        cube_id = self._focus_cube_id or self._active_cube_id
        addr = self._focus_addr
        if not cube_id or addr is None:
            self._summary.setText("Select a data cell to inspect circular paths.")
            self._cycle_meta.setText("Cycle 0 of 0")
            self._set_actions_enabled(False)
            return

        try:
            if self._session is None:
                raise RuntimeError("No session available for diagnostics_circular_references")
            analysis = self._session.query(
                "diagnostics_circular_references",
                cube_id=cube_id,
                addr=addr,
                max_depth=int(self._depth.value()),
            )
            if analysis is None:
                analysis = {}
        except Exception as exc:
            self._summary.setText(f"Circular analysis unavailable: {exc}")
            self._cycle_meta.setText("Cycle 0 of 0")
            self._set_actions_enabled(False)
            return

        self._analysis = analysis
        cycles = list(analysis.get("cycles") or [])
        root = analysis.get("root") or {}
        confidence = str(analysis.get("confidence") or "unknown").upper()
        root_label = str(root.get("addr_label") or "(selected cell)")

        if not cycles:
            self._summary.setText(
                f"Circular reference detected at {root_label} | confidence: {confidence} | no explicit cycle path found yet."
            )
            self._cycle_meta.setText("Cycle 0 of 0")
            self._set_actions_enabled(False)
            return

        cycle_count = int(analysis.get("cycle_count", len(cycles)))
        severity = "critical" if str(root.get("value")) == "#CIRC!" else "warning"
        self._summary.setText(
            f"Circular reference detected ({severity}) at {root_label} | confidence: {confidence} | cycles: {cycle_count}"
        )

        self._cycle_picker.blockSignals(True)
        for cycle in cycles:
            idx = int(cycle.get("index", 0)) + 1
            length = int(cycle.get("length", 0))
            self._cycle_picker.addItem(f"Cycle {idx} (length {length})")
        self._cycle_picker.blockSignals(False)
        self._cycle_picker.setCurrentIndex(0)
        self._load_cycle(0)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for btn in (
            self._btn_prev,
            self._btn_next,
            self._btn_copy,
            self._btn_open_trace,
            self._btn_focus_editable,
        ):
            btn.setEnabled(enabled)

    @QtCore.Slot(int)
    def _on_cycle_changed(self, index: int) -> None:
        self._load_cycle(index)

    def _load_cycle(self, index: int) -> None:
        cycles = list(self._analysis.get("cycles") or [])
        if not (0 <= index < len(cycles)):
            self._cycle_nodes = []
            self._nodes.clear()
            self._path.setPlainText("")
            self._cycle_meta.setText("Cycle 0 of 0")
            self._set_actions_enabled(False)
            return

        self._active_cycle_index = index
        cycle = cycles[index]
        self._cycle_nodes = list(cycle.get("nodes") or [])
        self._active_node_index = 0

        self._cycle_meta.setText(f"Cycle {index + 1} of {len(cycles)}")
        self._path.setPlainText(str(cycle.get("path") or ""))

        self._nodes.clear()
        for node_idx, node in enumerate(self._cycle_nodes):
            label = str(node.get("addr_label") or "")
            source = str(node.get("source") or "")
            entry = QtWidgets.QListWidgetItem(f"{node_idx + 1}. {label} [{source}]")
            cube_id = node.get("cube_id")
            addr = node.get("addr")
            if isinstance(cube_id, str) and isinstance(addr, (tuple, list)):
                entry.setData(QtCore.Qt.ItemDataRole.UserRole, (cube_id, tuple(addr)))
                entry.setFlags(entry.flags() | QtCore.Qt.ItemFlag.ItemIsSelectable)
            self._nodes.addItem(entry)

        self._set_actions_enabled(bool(self._cycle_nodes))
        if self._cycle_nodes:
            self._nodes.setCurrentRow(0)

    @QtCore.Slot(QtWidgets.QListWidgetItem)
    def _on_node_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not (isinstance(data, tuple) and len(data) == 2):
            return
        cube_id, addr = data
        if not isinstance(cube_id, str) or not isinstance(addr, tuple):
            return
        self.navigate_requested.emit(cube_id, addr)

    @QtCore.Slot(int)
    def _on_node_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self._active_node_index = row

    @QtCore.Slot()
    def _on_prev_node(self) -> None:
        if not self._cycle_nodes:
            return
        self._active_node_index = (self._active_node_index - 1) % len(self._cycle_nodes)
        self._nodes.setCurrentRow(self._active_node_index)
        item = self._nodes.item(self._active_node_index)
        if item is not None:
            self._on_node_activated(item)

    @QtCore.Slot()
    def _on_next_node(self) -> None:
        if not self._cycle_nodes:
            return
        self._active_node_index = (self._active_node_index + 1) % len(self._cycle_nodes)
        self._nodes.setCurrentRow(self._active_node_index)
        item = self._nodes.item(self._active_node_index)
        if item is not None:
            self._on_node_activated(item)

    @QtCore.Slot()
    def _copy_cycle_path(self) -> None:
        text = self._path.toPlainText().strip()
        if not text:
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(text)

    @QtCore.Slot()
    def _open_in_flow(self) -> None:
        root = self._analysis.get("root") or {}
        cube_id = root.get("cube_id")
        addr = root.get("addr")
        if isinstance(cube_id, str) and isinstance(addr, (tuple, list)):
            self.open_trace_requested.emit(cube_id, tuple(addr))

    @QtCore.Slot()
    def _focus_first_editable(self) -> None:
        for idx, node in enumerate(self._cycle_nodes):
            if not bool(node.get("editable_rule")):
                continue
            self._active_node_index = idx
            self._nodes.setCurrentRow(idx)
            cube_id = node.get("cube_id")
            addr = node.get("addr")
            if isinstance(cube_id, str) and isinstance(addr, (tuple, list)):
                self.navigate_requested.emit(cube_id, tuple(addr))
            return
