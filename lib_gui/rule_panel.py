from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
import logging

from lib_contracts.errors import CircularReferenceError
from lib_rulepanel import ChannelFilterBar, RuleListWidget, RuleData, ChannelMetrics
from lib_gui.workspace_read_model import WorkspaceReadModel

logger = logging.getLogger(__name__)


class RulePanel(QtWidgets.QWidget):
    rules_changed = QtCore.Signal()
    rule_reordered = QtCore.Signal()  # Lightweight signal for drag-drop (no rebuild needed)

    def __init__(
        self,
        *,
        session=None,
        parent: QtWidgets.QWidget | None = None,
        workspace_read_model=None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._workspace_read_model = workspace_read_model or WorkspaceReadModel(session) if session is not None else None
        # Cube whose rules/rules are currently shown. If None, we show all
        # cubes (legacy behaviour).
        self._active_cube_id: str | None = None

        # Dark header bar
        header = QtWidgets.QWidget()
        header.setStyleSheet("background-color: #111827;")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(12)
        
        self._title = QtWidgets.QLabel("Rules")
        self._title.setStyleSheet("color: white; font-size: 13px; font-weight: 600;")
        header_layout.addWidget(self._title)
        
        self._filter_label = QtWidgets.QLabel("all channels")
        self._filter_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        header_layout.addWidget(self._filter_label, stretch=1)
        
        self._count_label = QtWidgets.QLabel("0 total")
        self._count_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        header_layout.addWidget(self._count_label)
        
        header.setFixedHeight(32)
        
        # Channel filter bar
        self._pill_bar = ChannelFilterBar()
        self._pill_bar.setFixedHeight(32)
        self._pill_bar.filter_changed.connect(self._on_filter_changed)
        
        # Rule list (new widget from lib_rulepanel)
        self._list = RuleListWidget()
        self._list.edit_started.connect(self._on_edit_started)
        self._list.edit_ended.connect(self._on_edit_ended)
        self._list.rule_moved.connect(self._on_rule_moved)
        self._list.rule_edited.connect(self._on_rule_edited)
        self._list.context_menu_requested.connect(self._on_context_menu)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._pill_bar)
        layout.addWidget(self._list, 1)

        self.rebuild()

    def set_active_cube(self, cube_id: str | None) -> None:
        """Limit the panel to rules/rules for the given cube.

        Passing None restores the legacy behaviour of showing rules for all
        cubes. In normal UI usage this is wired to the cube of the currently
        selected view/tab.
        """
        logger.debug(f"set_active_cube: new={cube_id[:8] if cube_id else None}..., old={self._active_cube_id[:8] if self._active_cube_id else None}...")
        if cube_id == self._active_cube_id:
            logger.debug("  same cube, skipping rebuild")
            return
        self._active_cube_id = cube_id
        self.rebuild()

    @QtCore.Slot()
    def rebuild(self) -> None:
        """Rebuild the rule panel with current read-model data."""
        # Update title
        title = "Rules"
        cube = None
        if self._active_cube_id is not None and self._workspace_read_model is not None:
            cube = self._workspace_read_model.get_cube(self._active_cube_id)
        if cube is not None:
            cube_name = cube.get("name", cube.get("id", ""))
            if cube_name:
                title = f"Rules: {cube_name}"
        self._title.setText(title)

        # Get dimension names from read model
        dimension_names: list[str] = []
        if cube is not None:
            for dim_id in cube.get("dimension_ids", []):
                dim = self._workspace_read_model.get_dimension(dim_id)
                if dim is not None:
                    dimension_names.append(dim.get("name", dim_id))
                else:
                    dimension_names.append(dim_id)

        # Fetch rules from read-model query
        rules: list[dict] = []
        order: list[str] = []
        if self._session is not None:
            ws_rules_data = self._session.query("workspace_rules")
            if ws_rules_data:
                all_rules = ws_rules_data.get("rules", [])
                order = ws_rules_data.get("rule_order", [])
                if self._active_cube_id is not None:
                    rules = [r for r in all_rules if r.get("cube_id") == self._active_cube_id]
                else:
                    rules = all_rules
        logger.debug(f"rebuild: active_cube_id={self._active_cube_id}, rules={len(rules)}")

        # Build ordered rules list
        ordered_rules: list[dict] = []
        rules_by_id = {r.get("id", ""): r for r in rules}
        for rid in order:
            if rid in rules_by_id:
                ordered_rules.append(rules_by_id[rid])
        for r in rules:
            if r.get("id", "") not in order:
                ordered_rules.append(r)

        # Determine @ dimension slot from cube dimensions so precedence
        # computation can normalize implied @.value (None) to explicit at_value.
        cube_dim_ids = cube.get("dimension_ids", []) if cube is not None else []
        at_slot = cube_dim_ids.index("@") if "@" in cube_dim_ids else None

        # Compute precedence statuses for the current rule order
        precedence_statuses = self._compute_precedence_statuses(ordered_rules, at_slot=at_slot)

        # Convert to RuleData objects
        rule_data_list: list[RuleData] = []
        for idx, r in enumerate(ordered_rules):
            lhs = self._format_rule_lhs(r)
            expr = r.get("expression", "")
            # Derive channel from @ dimension target; default to @.value
            channel = "@.value"
            targets = r.get("targets")
            if targets:
                for dim_name, item_name in targets:
                    if dim_name == "@":
                        channel = f"@.{item_name}"
                        break
            raw_mask = tuple(r.get("addr_mask", [])) if r.get("addr_mask") else None
            # Normalize mask for display specificity (None in @ slot → at_value)
            norm_mask = raw_mask
            if at_slot is not None and raw_mask and at_slot < len(raw_mask) and raw_mask[at_slot] is None:
                lst = list(raw_mask)
                lst[at_slot] = "at_value"
                norm_mask = tuple(lst)
            norm_specificity = sum(1 for v in norm_mask if v is not None) if norm_mask else 0
            rule_data_list.append(RuleData.from_mock(
                lhs=lhs,
                rhs=expr,
                channel=channel,
                rule_id=r.get("id"),
                dimension_names=dimension_names,
                status=precedence_statuses[idx],
                cube_id=r.get("cube_id"),
                addr_mask=raw_mask,
                rule_index=idx + 1,
                specificity=norm_specificity,
            ))

        # Count rules per channel for pill bar
        channel_counts: dict[str, int] = {}
        for rd in rule_data_list:
            channel_counts[rd.channel] = channel_counts.get(rd.channel, 0) + 1

        # Build channel metrics for pills
        all_channels = ["@.value", "@.fill", "@.format_number", "@.font_family",
                       "@.font_color", "@.font_size", "@.font_weight", "@.font_italic",
                       "@.format_text", "@.format_null", "@.format_error",
                       "@.text_h_align", "@.text_v_align", "@.text_indent", "@.text_wrap",
                       "@.comment"]
        channel_data = [
            ChannelMetrics(
                channel_id=ch,
                icon_name="",  # Will be resolved by ChannelPill
                count=channel_counts.get(ch, 0),
                context_matches=0,  # TODO: compute from selection
                viewport_matches=channel_counts.get(ch, 0)
            )
            for ch in all_channels
        ]
        self._pill_bar.set_channel_data(channel_data)

        # Set rules on list
        self._list.set_rules(rule_data_list)
        self._count_label.setText(f"{len(rule_data_list)} total")

    def _format_addr(self, cube_id: str, addr: tuple[str, ...]) -> str:
        """Format address tuple to readable string."""
        if self._workspace_read_model is None:
            return ", ".join(addr)
        cube = self._workspace_read_model.get_cube(cube_id)
        if cube is None:
            return ", ".join(addr)
        parts: list[str] = []
        dim_ids = cube.get("dimension_ids", [])
        for i, item_id in enumerate(addr):
            if i >= len(dim_ids):
                parts.append("#REF!.#REF!")
                continue
            dim_id = dim_ids[i]
            dim = self._workspace_read_model.get_dimension(dim_id)
            if dim is None:
                parts.append(item_id)
                continue
            items = dim.get("items", [])
            found = next((it for it in items if it.get("id") == item_id), None)
            dim_name = dim.get("name", dim_id)
            if found is None:
                parts.append(f"{dim_name}.#REF!")
            else:
                parts.append(f"{dim_name}.{found.get('name', item_id)}")
        return ", ".join(parts)

    @staticmethod
    def _compute_precedence_statuses(rules: list, at_slot: int | None = None) -> list[str]:
        """Compute 'Overrides #N' / 'Overridden by #N' status strings.

        Rules must be objects with ``cube_id``, ``specificity`` and
        ``index`` (position in the list).  For engine rules, specificity
        is derived from ``addr_mask``; for RuleData objects the
        ``specificity`` attribute is used directly.

        ``at_slot`` is the index of the ``@`` dimension in the cube's
        ``dimension_ids``.  When provided, a ``None`` in that slot is
        normalised to ``at_value`` so implied-channel and explicit-channel
        rules compare equally (matching the engine's ``_effective_rule_mask``
        behaviour).
        """

        def _val(obj, attr, default=None):
            """Read ``attr`` from a dict (via ``.get``) or an object (via ``getattr``)."""
            if hasattr(obj, "get"):
                return obj.get(attr, default)
            return getattr(obj, attr, default)

        def _masks_overlap(ma, mb) -> bool:
            """Return True if two masks can apply to the same address."""
            if not ma or not mb:
                return False  # cannot determine overlap without masks
            max_len = max(len(ma), len(mb))
            a = list(ma) + [None] * (max_len - len(ma))
            b = list(mb) + [None] * (max_len - len(mb))
            return all(x is None or y is None or x == y for x, y in zip(a, b))

        def _normalize_mask(mask: tuple, at_slot: int | None) -> tuple:
            """Replace None in @ slot with at_value so implied/explicit channel match."""
            if at_slot is None or not mask:
                return mask
            if at_slot < len(mask) and mask[at_slot] is None:
                lst = list(mask)
                lst[at_slot] = "at_value"
                return tuple(lst)
            return mask

        # Build metadata with normalized masks.
        # Specificity is computed from the *normalized* mask so that implied
        # @.value (None → at_value) and explicit @.value get the same count,
        # matching the engine's _effective_rule_mask runtime behaviour.
        rule_meta = []
        for i, r in enumerate(rules):
            addr_mask = _normalize_mask(_val(r, "addr_mask") or (), at_slot)
            spec = sum(1 for v in addr_mask if v is not None)
            rule_meta.append({
                "index": i,
                "cube_id": _val(r, "cube_id", None),
                "specificity": spec,
                "addr_mask": addr_mask,
            })

        statuses: list[str] = []
        for i, meta in enumerate(rule_meta):
            cube_id = meta["cube_id"]
            if not cube_id:
                statuses.append("<Unique>")
                continue

            my_spec = meta["specificity"]
            my_order = meta["index"]
            my_mask = meta["addr_mask"]
            overrules: list[int] = []
            overruled_by: list[int] = []

            for j, other in enumerate(rule_meta):
                if i == j:
                    continue
                if other["cube_id"] != cube_id:
                    continue
                if not _masks_overlap(my_mask, other["addr_mask"]):
                    continue  # these rules can never conflict

                other_spec = other["specificity"]
                other_order = other["index"]

                if my_spec > other_spec:
                    overrules.append(j + 1)
                elif my_spec < other_spec:
                    overruled_by.append(j + 1)
                elif my_order > other_order:
                    overrules.append(j + 1)
                else:
                    overruled_by.append(j + 1)

            if overrules and not overruled_by:
                status = f"Overrides {', '.join(f'#{n}' for n in overrules)}"
            elif overruled_by and not overrules:
                status = f"Overridden by {', '.join(f'#{n}' for n in overruled_by)}"
            elif overrules and overruled_by:
                status = (
                    f"Overrides {', '.join(f'#{n}' for n in overrules)}; "
                    f"Overridden by {', '.join(f'#{n}' for n in overruled_by)}"
                )
            else:
                status = "<Unique>"

            statuses.append(status)

        return statuses

    def _format_rule_lhs(self, rule: object) -> str:
        """Format rule LHS for display. Accepts dict-like or RuleData input."""
        if not hasattr(rule, "get"):
            return ""

        cube_id = rule.get("cube_id")
        cube_name = ""
        if cube_id and self._workspace_read_model is not None:
            cube = self._workspace_read_model.get_cube(cube_id)
            if cube is not None:
                cube_name = cube.get("name", cube_id)

        def whole_cube_label() -> str:
            return f"{cube_name}::*.*" if cube_name else "*.*"

        targets = rule.get("targets")
        if targets:
            target_parts: list[str] = []
            all_wildcards = True
            for dim_name, item_name in targets:
                if item_name == "*":
                    target_parts.append(f"{dim_name}.*")
                elif item_name.upper() in {"THIS", "PREV", "NEXT", "FIRST", "LAST"}:
                    target_parts.append(f"{dim_name}[{item_name}]")
                    all_wildcards = False
                else:
                    target_parts.append(f"{dim_name}.{item_name}")
                    all_wildcards = False

            # If all targets are wildcards, use whole-cube format
            if not target_parts or all_wildcards:
                return whole_cube_label()
            if len(target_parts) == 1:
                result = target_parts[0]
            else:
                result = "[" + ", ".join(target_parts) + "]"

            if rule.get("is_anchored"):
                result = "$" + result
            return result

        addr_mask = rule.get("addr_mask")
        cube_dim_ids = []
        if cube_id and self._workspace_read_model is not None:
            cube = self._workspace_read_model.get_cube(cube_id)
            if cube is not None:
                cube_dim_ids = cube.get("dimension_ids", [])

        if not cube_dim_ids or addr_mask is None or len(addr_mask) != len(cube_dim_ids):
            if addr_mask:
                for i, mask_item in enumerate(addr_mask):
                    if mask_item is not None and mask_item != "#REF!":
                        if i < len(cube_dim_ids):
                            check_dim = self._workspace_read_model.get_dimension(cube_dim_ids[i])
                            if check_dim is not None:
                                items = check_dim.get("items", [])
                                found_item = next((it.get("name") for it in items if it.get("id") == mask_item), None)
                                if found_item:
                                    return f"#REF!.{found_item}"
            return "#REF!"

        parts: list[str] = []
        for dim_id, item_id in zip(cube_dim_ids, addr_mask):
            if item_id is None:
                continue
            dim = self._workspace_read_model.get_dimension(dim_id) if self._workspace_read_model else None
            if dim is None:
                parts.append(item_id)
                continue
            # Handle @ technical dimension specially - show as @.channel
            if dim_id == "@":
                if item_id.startswith("@."):
                    channel_name = item_id[2:]  # Remove "@." prefix
                    parts.append(f"@.{channel_name}")
                else:
                    parts.append(item_id)
                continue
            items = dim.get("items", [])
            item_name = next((it.get("name", item_id) for it in items if it.get("id") == item_id), item_id)
            dim_name = dim.get("name", dim_id)
            parts.append(f"{dim_name}.{item_name}")

        if not parts:
            result = whole_cube_label()
        elif len(parts) == 1:
            result = parts[0]
        else:
            result = "[" + ", ".join(parts) + "]"

        if rule.get("is_anchored"):
            result = "$" + result
        return result

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        # TODO: Re-implement for new widget
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Cancel any active edit when double-clicking outside the rule list."""
        # Check if double-click was inside the rule list
        if self._list.geometry().contains(event.position().toPoint()):
            # Let the list handle it (starts editing)
            super().mouseDoubleClickEvent(event)
            return
        
        # Double-click was outside the list (header, pill bar, empty area)
        # Cancel any active edit
        editing_row = self._list.get_editing_row()
        if editing_row:
            editing_row.cancel_edit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def highlight_for_cell(self, cube_id: str, addr: tuple[str, ...]) -> None:
        """Highlight rules that affect the selected cell (bold them)."""
        winning_rule_id: str | None = None
        if self._session is not None:
            data = self._session.query("cell_rule", cube_id=cube_id, addr=addr)
            if data and data.get("expression") is not None:
                # Find the matching rule in the currently displayed rules by expression.
                expr = data.get("expression")
                for rd in self._list.rules:
                    if rd.cube_id == cube_id and rd.rhs == expr:
                        winning_rule_id = rd.rule_id
                        break

        for row in self._list.row_widgets:
            rule_id = row.rule_body.rule_id
            if not rule_id:
                continue

            # Bold if this row's rule is the anchored winning rule for this cell
            label_widget = None
            if hasattr(row, "row_layout"):
                for i in range(row.row_layout.count()):
                    item = row.row_layout.itemAt(i)
                    w = item.widget()
                    if w is not None and isinstance(w, QtWidgets.QLabel) and w != row.num_label:
                        label_widget = w
                        break
            if winning_rule_id is not None and winning_rule_id == rule_id:
                if label_widget is not None:
                    label_widget.setStyleSheet("font-weight: bold;")
            else:
                if label_widget is not None:
                    label_widget.setStyleSheet("")

    # -------------------------------------------------------------------------
    # New signal handlers for lib_rulepanel integration
    # -------------------------------------------------------------------------
    def _on_filter_changed(self, selected_channels: set) -> None:
        """Handle channel filter change."""
        self._list.refresh_list(selected_channels if selected_channels else None)
        count = len([f for f in self._list.rules
                    if not selected_channels or f.channel in selected_channels])
        self._count_label.setText(f"{count} total")
        if selected_channels:
            self._filter_label.setText(", ".join(sorted(selected_channels)))
        else:
            self._filter_label.setText("all channels")

    def _on_edit_started(self) -> None:
        """Handle rule edit started."""
        self._pill_bar.setEnabled(False)

    def _on_edit_ended(self) -> None:
        """Handle rule edit ended."""
        self._pill_bar.setEnabled(True)

    def _on_rule_moved(self, source_idx: int, target_idx: int) -> None:
        """Handle rule reordering via drag-drop."""
        # Collect rule IDs in new order directly from displayed rules
        rule_ids: list[str] = []
        for rule in self._list.rules:
            if rule.rule_id:
                rule_ids.append(rule.rule_id)
        
        if rule_ids:
            if not (hasattr(self, '_session') and self._session):
                raise RuntimeError("No session available for set_rule_order")
            result = self._session.execute("set_rule_order", rule_ids=rule_ids)
            if result.status.name == "ERROR":
                # Roll back visual order on failure
                self.rebuild()
                return

        # Recompute precedence statuses for the new visual order
        at_slot = None
        if self._active_cube_id and self._workspace_read_model is not None:
            cube = self._workspace_read_model.get_cube(self._active_cube_id)
            if cube is not None:
                cube_dim_ids = cube.get("dimension_ids", [])
                at_slot = cube_dim_ids.index("@") if "@" in cube_dim_ids else None
        new_statuses = self._compute_precedence_statuses(self._list.rules, at_slot=at_slot)
        for idx, rule in enumerate(self._list.rules):
            rule.status = new_statuses[idx]
            # row_widgets is still in the OLD order here (_finish_animation
            # runs on a timer after us), so match by rule identity.
            for row in self._list.row_widgets:
                if row.rule_body is rule and hasattr(row, "meta_label"):
                    if row.meta_label is not None:
                        row.meta_label.setText(rule.status)
                        if rule.status and rule.status != "<Unique>":
                            row.meta_line.show()
                        else:
                            row.meta_line.hide()
                    break

        # Don't emit rules_changed - it triggers a full rebuild which resets selection.
        # The visual list is already reordered by _finish_animation().
        # Just emit a lightweight signal for dirty marking.
        self.rule_reordered.emit()

    def _on_rule_edited(self, rule: RuleData) -> None:
        """Handle rule edited inline."""
        if not rule.rule_id:
            return
        
        # Parse LHS = RHS format
        text = f"{rule.lhs} = {rule.rhs}"
        import re
        m = re.match(r"^=?\s*(.*?)\s*=\s*(.+)$", text)
        if not m:
            return
            
        lhs_raw = m.group(1).strip()
        expr_new = m.group(2).strip()
        logger.debug(f"_on_rule_edited: text='{text}', lhs_raw='{lhs_raw}', expr_new='{expr_new}'")

        # Detect $ anchor prefix for anchored rules
        is_anchored = False
        if lhs_raw.startswith("$"):
            is_anchored = True
            lhs_raw = lhs_raw[1:].strip()
            logger.debug(f"detected $ anchor, is_anchored=True, stripped lhs='{lhs_raw}'")

        # Use cube_id stored in RuleData during rebuild()
        cube_id = rule.cube_id if rule.cube_id else self._active_cube_id
        try:
            if not (hasattr(self, '_session') and self._session):
                raise RuntimeError("No session available for update_rule")
            resolve = self._session.query("rule_target_resolve", cube_id=cube_id, lhs=lhs_raw)
            if resolve.get("error"):
                raise RuntimeError(resolve["error"])
            targets = resolve["targets"]
            logger.debug(f"rule_target_resolve succeeded: {targets}")
            result = self._session.execute(
                "update_rule",
                rule_id=rule.rule_id,
                targets=targets,
                expression=expr_new,
                is_anchored=is_anchored,
            )
            if result.status.name == "ERROR":
                raise RuntimeError(result.error)
            logger.debug("update_rule_full completed")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Rule error", str(e))
            return
        
        # Track which rule was edited to restore selection after rebuild
        edited_rule_id = rule.rule_id
        edited_lhs = rule.lhs  # Fallback for matching
        self.rebuild()
        # Restore selection to the edited rule
        selected = False
        if edited_rule_id:
            for row in self._list.row_widgets:
                if row.rule_body.rule_id == edited_rule_id:
                    self._list.select_row(row)
                    selected = True
                    break
        # Fallback: match by LHS if rule_id not found
        if not selected and edited_lhs:
            for row in self._list.row_widgets:
                if row.rule_body.lhs == edited_lhs:
                    self._list.select_row(row)
                    break
        self.rules_changed.emit()

    def _on_context_menu(self, rule: RuleData, global_pos: QtCore.QPoint) -> None:
        """Show context menu for rule row."""
        menu = QtWidgets.QMenu(self)
        
        edit_action = menu.addAction("Edit...")
        delete_action = menu.addAction("Delete")
        menu.addSeparator()
        copy_action = menu.addAction("Copy Rule")
        
        action = menu.exec(global_pos)
        
        if action == edit_action:
            # Find the row and start edit
            for row in self._list.row_widgets:
                if row.rule_body is rule:
                    self._list.start_row_edit(row)
                    break
        elif action == delete_action:
            self._delete_rule(rule)
        elif action == copy_action:
            # Copy to clipboard
            text = f"{rule.lhs} = {rule.rhs}"
            QtWidgets.QApplication.clipboard().setText(text)

    def _delete_rule(self, rule: RuleData) -> None:
        """Delete a rule."""
        if not rule.rule_id:
            return

        removed = False
        if not (hasattr(self, '_session') and self._session):
            raise RuntimeError("No session available for delete_rule")
        result = self._session.execute("delete_rule", rule_id=rule.rule_id)
        if result.status.name == "ERROR":
            # Resync on failure
            self.rebuild()
            return
        removed = result.status.name == "SUCCESS"

        if removed:
            self.rebuild()
            self.rules_changed.emit()
