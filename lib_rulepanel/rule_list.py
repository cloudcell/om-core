"""Rule list widget with scrollable rows."""
from __future__ import annotations

from typing import List, Set, Optional

from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QLabel, 
    QFrame, QApplication
)
from PySide6.QtCore import Qt, Signal, QPoint, QTimer

from .rule_models import RuleData
from .rule_row import EditableRuleRow


class RuleListWidget(QScrollArea):
    """Scrollable list of rules with drag-drop support."""

    edit_started = Signal()  # Emitted when any row starts editing
    edit_ended = Signal()    # Emitted when any row ends editing
    rule_moved = Signal(int, int)  # source_idx, target_idx
    rule_edited = Signal(RuleData)  # Rule was edited
    context_menu_requested = Signal(RuleData, QPoint)  # rule, position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: List[RuleData] = []
        self.selected_row: Optional[EditableRuleRow] = None
        self.row_widgets: List[EditableRuleRow] = []
        self._drop_indicator: Optional[QFrame] = None
        self._insert_index: int = -1
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the scroll area."""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QScrollArea {
                background-color: white;
                border: none;
            }
            QScrollBar:vertical {
                background: #F3F4F6;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #9CA3AF;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #6B7280;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(12, 8, 12, 8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.setWidget(self.container)
        
    def set_rules(self, rules: List[RuleData]):
        """Set the list of rules to display."""
        self.rules = rules
        self.refresh_list()
        
    def refresh_list(self, filter_channels: Optional[Set[str]] = None):
        """Refresh the rule list with optional filter."""
        # Preserve selected rule identity before clearing
        selected_rule_id = None
        if self.selected_row and self.selected_row.rule_body:
            selected_rule_id = self.selected_row.rule_body.rule_id

        # Clear existing
        self.row_widgets = []
        self.selected_row = None
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        # Filter rules by channel
        filtered = self.rules
        if filter_channels:
            filtered = [f for f in self.rules if f.channel in filter_channels]

        # All cell rules converted to anchored rules (cell rules converted to anchored rules)
        row_idx = 0
        restored_selection = False

        for rule in filtered:
            is_selected = (row_idx == 0) if not selected_rule_id else False
            row = self._create_row(rule, is_selected, row_idx)
            self.layout.addWidget(row)
            self.row_widgets.append(row)
            if is_selected:
                self.selected_row = row
            # Restore selection to previously selected rule if it still exists
            if selected_rule_id and rule.rule_id == selected_rule_id:
                self.select_row(row)
                restored_selection = True
            row_idx += 1

        # If selection was not restored (rule filtered out), default to first row
        if not restored_selection and self.row_widgets:
            self.select_row(self.row_widgets[0])

        # Add stretch at bottom
        self.layout.addStretch()
        
    def _create_row(self, rule: RuleData, is_selected: bool, row_index: int) -> EditableRuleRow:
        """Create a rule row widget."""
        is_even = (row_index % 2) == 0
        display_number = rule.rule_index if rule.rule_index > 0 else row_index + 1
        row = EditableRuleRow(rule, is_selected, is_even, display_number)
        row.dropped_on.connect(self._on_row_dropped)
        row.context_menu_requested.connect(lambda global_pos: self._on_row_context_menu(row, global_pos))
        return row

    def _on_row_context_menu(self, row: EditableRuleRow, global_pos: QPoint):
        """Forward context menu request with rule data and global position."""
        self.context_menu_requested.emit(row.rule_body, global_pos)
        
    def _on_row_dropped(self, source_row: EditableRuleRow, insert_idx: int):
        """Handle row dropped from another row."""
        # Find source index
        source_idx = None
        for i, row in enumerate(self.row_widgets):
            if row is source_row:
                source_idx = i
                break
        
        if source_idx is not None and source_idx != insert_idx:
            if source_idx < insert_idx:
                insert_idx -= 1
            self._move_rule(source_idx, insert_idx)
            
    def select_row(self, row: EditableRuleRow):
        """Select a rule row (deselects others)."""
        if self.is_any_row_editing() and not row.is_editing:
            return

        if self.selected_row and self.selected_row != row:
            try:
                self.selected_row.is_selected = False
                self.selected_row.update_style()
            except RuntimeError:
                pass

        self.selected_row = row
        row.is_selected = True
        row.update_style()
        
    def start_row_edit(self, row: EditableRuleRow):
        """Start editing a row."""
        current_edit = self.get_editing_row()
        if current_edit and current_edit != row:
            current_edit.cancel_edit()

        if row.is_editing:
            return

        row.is_editing = True
        self.select_row(row)
        row.clear_layout()
        row.setup_edit_mode()
        self.edit_started.emit()
        
    def end_row_edit(self, row: EditableRuleRow):
        """End editing."""
        was_editing = row.is_editing
        row.is_editing = False
        if was_editing:
            self.edit_ended.emit()
            self.rule_edited.emit(row.rule_body)
        # Keep the row selected after editing ends
        self.select_row(row)
        
    def is_any_row_editing(self) -> bool:
        """Check if any row is currently in edit mode."""
        return self.get_editing_row() is not None

    def get_editing_row(self) -> Optional[EditableRuleRow]:
        """Get the row currently in edit mode, or None."""
        for row in self.row_widgets:
            if row.is_editing:
                return row
        return None

    def _move_rule(self, source_idx: int, target_idx: int):
        """Move rule from source to target index with animation."""
        if 0 <= source_idx < len(self.rules) and 0 <= target_idx < len(self.rules):
            self._animate_drop_move(source_idx, target_idx)
            
    def _animate_drop_move(self, source_idx: int, target_idx: int):
        """Animate drag-drop: dragged row flies to destination while others slide."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QTimer
        
        duration = 200
        
        # Capture original positions BEFORE any changes
        old_geoms = {id(row.rule_body): row.geometry() for row in self.row_widgets}
        rule_to_row = {id(row.rule_body): row for row in self.row_widgets}
        dragged_rule = self.rules[source_idx]
        dragged_row = rule_to_row.get(id(dragged_rule))
        
        if not dragged_row:
            # Fallback: no animation
            rule = self.rules.pop(source_idx)
            self.rules.insert(target_idx, rule)
            self.rule_moved.emit(source_idx, target_idx)
            self.refresh_list()
            return
        
        dragged_geom = old_geoms.get(id(dragged_rule))
        dragged_height = dragged_geom.height() if dragged_geom else dragged_row.height()
        layout_spacing = self.layout.spacing()
        gap_height = dragged_height + layout_spacing
        
        # Calculate ALL target positions BEFORE moving data
        target_positions = {}  # rule_id_key -> (row, target_y)
        
        if source_idx < target_idx:
            # Moving DOWN
            target_row = self.row_widgets[target_idx]
            target_row_geom = old_geoms.get(id(target_row.rule_body))
            target_row_height = target_row_geom.height() if target_row_geom else dragged_height
            dragged_target_y = target_row_geom.y() + target_row_height - dragged_height if target_row_geom else 0
            
            for i, row in enumerate(self.row_widgets):
                old_geom = old_geoms.get(id(row.rule_body))
                if not old_geom:
                    continue
                if row is dragged_row:
                    target_positions[id(row.rule_body)] = (row, dragged_target_y)
                elif source_idx < i <= target_idx:
                    new_y = old_geom.y() - gap_height
                    target_positions[id(row.rule_body)] = (row, new_y)
        else:
            # Moving UP
            target_row = self.row_widgets[target_idx]
            target_row_geom = old_geoms.get(id(target_row.rule_body))
            dragged_target_y = target_row_geom.y() if target_row_geom else 0
            
            for i, row in enumerate(self.row_widgets):
                old_geom = old_geoms.get(id(row.rule_body))
                if not old_geom:
                    continue
                if row is dragged_row:
                    target_positions[id(row.rule_body)] = (row, dragged_target_y)
                elif target_idx <= i < source_idx:
                    target_positions[id(row.rule_body)] = (row, old_geom.y() + gap_height)
        
        # Freeze updates and layout
        content = self.widget()
        if content:
            content.setUpdatesEnabled(False)
        self.layout.setEnabled(False)
        
        # Detach ALL rows from layout at their original positions
        for row in self.row_widgets:
            old_geom = old_geoms.get(id(row.rule_body))
            if old_geom:
                row.move(old_geom.x(), old_geom.y())
        
        # Hide drop indicator BEFORE animation starts
        self.hide_drop_indicator()
        
        # NOW perform the data move
        rule = self.rules.pop(source_idx)
        self.rules.insert(target_idx, rule)
        
        # Raise dragged row to top
        if dragged_row:
            dragged_row.raise_()
        
        # Animate ALL rows simultaneously to their targets
        for rule_id_key, (row, target_y) in target_positions.items():
            old_geom = old_geoms.get(rule_id_key)
            if not old_geom:
                continue
            if abs(old_geom.y() - target_y) > 1:
                anim = QPropertyAnimation(row, b"pos", row)
                anim.setDuration(duration)
                anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
                anim.setStartValue(QPoint(old_geom.x(), old_geom.y()))
                anim.setEndValue(QPoint(old_geom.x(), target_y))
                anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        
        # Re-enable layout
        self.layout.setEnabled(True)
        
        if content:
            content.setUpdatesEnabled(True)
        
        # After animation completes, refresh to clean state
        QTimer.singleShot(duration + 50, lambda: self._finish_animation())
        
        self.rule_moved.emit(source_idx, target_idx)

    def _finish_animation(self):
        """Complete animation by reordering widgets in layout."""
        # Build new row_widgets list based on rules order
        rule_to_row = {id(row.rule_body): row for row in self.row_widgets}
        new_row_widgets = []

        for idx, rule in enumerate(self.rules):
            row = rule_to_row.get(id(rule))
            if row:
                # Guard against deleted C++ objects (test cleanup)
                try:
                    _ = row.is_even  # Test access
                except RuntimeError:
                    continue
                new_row_widgets.append(row)
                # Reset layout constraints
                row.setMinimumHeight(0)
                row.setMaximumHeight(16777215)
                row.setMinimumWidth(0)
                row.setMaximumWidth(16777215)
                # Recalculate zebra shading based on new position
                row.is_even = (idx % 2) == 0
                row.row_number = idx + 1
                row.update_style()

        self.row_widgets = new_row_widgets
        
        # Reorder widgets in the actual layout
        for row in self.row_widgets:
            self.layout.removeWidget(row)
            self.layout.addWidget(row, alignment=Qt.AlignmentFlag.AlignTop)
        
        # Remove any existing stretch/spacer at bottom and add fresh one
        i = 0
        while i < self.layout.count():
            item = self.layout.itemAt(i)
            if item and item.spacerItem():
                self.layout.removeItem(item)
            else:
                i += 1
        self.layout.addStretch(1)
        
        # Ensure drop indicator is hidden after animation
        self.hide_drop_indicator()
            
    def dragEnterEvent(self, event):
        """Accept drags from rule rows."""
        source = event.source()
        if isinstance(source, EditableRuleRow):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Show indicator at nearest boundary."""
        source = event.source()
        if isinstance(source, EditableRuleRow):
            event.acceptProposedAction()
            content = self.widget()
            if content:
                mouse_pos = event.position().toPoint()
                mouse_in_content = self.viewport().mapTo(content, mouse_pos)
                self.show_drop_indicator_at(mouse_in_content.y())

    def dropEvent(self, event):
        """Handle drop."""
        source = event.source()
        # Always hide indicator first thing
        self.hide_drop_indicator()
        
        if isinstance(source, EditableRuleRow):
            insert_idx = getattr(self, '_insert_index', -1)
            if insert_idx >= 0:
                source_idx = None
                for i, row in enumerate(self.row_widgets):
                    if row is source:
                        source_idx = i
                        break
                if source_idx is not None and source_idx != insert_idx:
                    if source_idx < insert_idx:
                        insert_idx -= 1
                    self._move_rule(source_idx, insert_idx)
            event.acceptProposedAction()

    def show_drop_indicator_at(self, mouse_y: int):
        """Show drop indicator at the nearest row boundary."""
        if not self.row_widgets:
            return
        
        content = self.widget()
        if not content:
            return
        
        boundaries = []
        for row in self.row_widgets:
            row_top = row.mapTo(content, QPoint(0, 0)).y()
            boundaries.append(row_top)
        if self.row_widgets:
            last_row = self.row_widgets[-1]
            last_bottom = last_row.mapTo(content, QPoint(0, 0)).y() + last_row.height()
            boundaries.append(last_bottom)
        
        if not boundaries:
            return
        
        nearest_idx = 0
        nearest_dist = abs(mouse_y - boundaries[0])
        for i, y in enumerate(boundaries):
            dist = abs(mouse_y - y)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = i
        
        self._insert_index = nearest_idx
        
        if self._drop_indicator is None:
            self._drop_indicator = QFrame(content)
            self._drop_indicator.setFixedHeight(2)
            self._drop_indicator.setStyleSheet("background-color: #3B82F6;")
            self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._drop_indicator.setWindowFlags(Qt.WindowType.Widget)
        
        indicator_y = boundaries[nearest_idx] - 1
        self._drop_indicator.move(0, indicator_y)
        self._drop_indicator.setFixedWidth(content.width())
        self._drop_indicator.show()
        self._drop_indicator.raise_()

    def hide_drop_indicator(self):
        """Hide and destroy the drop indicator line."""
        if self._drop_indicator:
            self._drop_indicator.hide()
            self._drop_indicator.deleteLater()
            self._drop_indicator = None
        self._insert_index = -1
            
    def dragLeaveEvent(self, event):
        """Hide indicator when leaving."""
        self.hide_drop_indicator()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to start editing or switch editing rows."""
        pos = event.position().toPoint()
        
        # Check if we have an editing row
        editing_row = self.get_editing_row()
        
        # First, find which row (if any) was clicked
        clicked_row = None
        for row in self.row_widgets:
            row_pos = row.mapTo(self, row.rect().topLeft())
            row_rect = row.rect().translated(row_pos)
            if row_rect.contains(pos):
                clicked_row = row
                break
        
        if editing_row:
            # Check if double-click was inside the editing row
            row_pos = editing_row.mapTo(self, editing_row.rect().topLeft())
            row_rect = editing_row.rect().translated(row_pos)
            
            if row_rect.contains(pos):
                # Click inside editing row - let it handle
                super().mouseDoubleClickEvent(event)
                return
            
            # Click outside editing row - cancel current edit
            editing_row.cancel_edit()
            
            # Only start editing a different row if one was actually clicked
            if clicked_row and clicked_row is not editing_row:
                self.start_row_edit(clicked_row)
                return
            # If clicked on header/empty space, just cancel and stop
            event.accept()
            return
        else:
            # No row editing - start edit only if a row was clicked
            if clicked_row:
                self.start_row_edit(clicked_row)
                return
        
        super().mouseDoubleClickEvent(event)
