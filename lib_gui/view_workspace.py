from __future__ import annotations

from PySide6 import QtCore, QtWidgets, QtGui

from lib_gui.calculation_flow_panel import CalculationFlowPanel
from lib_gui.circular_refs_panel import CircularReferencesPanel
from lib_gui.editable_tab_bar import EditableTabBar
from lib_gui.rule_panel import RulePanel
from lib_gui.draggable_rule_bar import DraggableRuleBar
class ViewWorkspacePane(QtWidgets.QWidget):
    """Reusable widget containing the draggable rule bar, view tabs, and rule panel."""

    def __init__(
        self,
        *,
        session=None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session

        # Draggable rule bar tile
        self._rule_bar_tile = DraggableRuleBar(self)
        
        # Drop zones for drag repositioning
        self._setup_drop_zones()

        # Tabbed view area
        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.setTabsClosable(False)
        
        # Install custom tab bar for inline editing
        editable_tab_bar = EditableTabBar(self._tabs)
        editable_tab_bar.setMovable(True)  # Must set on tab bar itself, not just QTabWidget
        self._tabs.setTabBar(editable_tab_bar)
        self._tabs.setStyleSheet(
            """
QTabBar::tab {
    border: 1px solid transparent;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #d8dce4;
    color: #1f1f1f;
    border-color: #b8bcc4;
}

QTabBar::tab:!selected {
    background-color: #f4f5f7;
    color: #202020;
    border-color: #c8ccd4;
}
            """
        )

        self._rule_panel = RulePanel(session=session, parent=self)
        self._flow_panel = CalculationFlowPanel(session=session, parent=self)
        self._circular_refs_panel = CircularReferencesPanel(session=session, parent=self)

        self._lower_tabs = QtWidgets.QTabWidget(self)
        self._lower_tabs.setDocumentMode(True)
        self._lower_tabs.setMovable(True)
        self._lower_tabs.setTabsClosable(False)
        self._lower_tabs.addTab(self._rule_panel, "Rule Panel")
        self._lower_tabs.addTab(self._flow_panel, "Calculation Flow")
        self._lower_tabs.addTab(self._circular_refs_panel, "Circular References")

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self._splitter.addWidget(self._tabs)
        self._splitter.addWidget(self._lower_tabs)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([420, 140])

        # Main layout with draggable rule bar at top (initially)
        self._main_layout = QtWidgets.QVBoxLayout(self)
        self._main_layout.setContentsMargins(6, 6, 6, 6)
        self._main_layout.setSpacing(6)
        self._main_layout.addWidget(self._rule_bar_tile)
        self._main_layout.addWidget(self._splitter, 1)
        
    def _setup_drop_zones(self):
        """Set up drop zone handling for the rule bar tile."""
        # Enable drops on this widget (workspace) to receive rule bar drags
        self.setAcceptDrops(True)
        
        # Create visual drop indicators
        self._drop_indicator_top = self._create_drop_indicator()
        self._drop_indicator_between = self._create_drop_indicator()
        self._drop_indicator_bottom = self._create_drop_indicator()
        
    def _create_drop_indicator(self) -> QtWidgets.QFrame:
        """Create a visual drop zone indicator line."""
        indicator = QtWidgets.QFrame(self)
        indicator.setFixedHeight(3)
        indicator.setStyleSheet("background-color: #3B82F6; border-radius: 1px;")
        indicator.hide()
        return indicator
        
    def _show_drop_indicator(self, indicator: QtWidgets.QFrame, y_pos: int):
        """Show drop indicator at specified Y position."""
        # Use the splitter's y position as reference for top/between indicators
        # For bottom indicator, position just above the bottom of the splitter
        indicator.setGeometry(4, y_pos, self.width() - 8, 3)
        indicator.show()
        indicator.raise_()
        
    def resizeEvent(self, event):
        """Update indicator widths on resize."""
        super().resizeEvent(event)
        # Update any visible indicator widths
        for indicator in [self._drop_indicator_top, self._drop_indicator_between, self._drop_indicator_bottom]:
            if indicator.isVisible():
                geo = indicator.geometry()
                indicator.setGeometry(4, geo.y(), self.width() - 8, 3)
        
    def _hide_all_drop_indicators(self):
        """Hide all drop indicators."""
        self._drop_indicator_top.hide()
        self._drop_indicator_between.hide()
        self._drop_indicator_bottom.hide()
        
    def _move_rule_bar_to_top(self):
        """Move rule bar to top position (above grid) - DEFAULT position."""
        # Only move if not already at top
        if getattr(self._rule_bar_tile, '_current_position', None) == "top":
            return
            
        # Hide from splitter first (QSplitter doesn't have removeWidget)
        self._rule_bar_tile.hide()
        self._rule_bar_tile.setParent(None)
        
        # Remove from main layout if present
        self._main_layout.removeWidget(self._rule_bar_tile)
        
        # Set minimum height for consistency, allow expansion for multi-line
        # Base: margins (4+4) + input (20) + padding = ~30px
        self._rule_bar_tile.setMinimumHeight(30)
        self._rule_bar_tile.setMaximumHeight(16777215)
        
        # Show and insert at top of main layout (index 0)
        self._rule_bar_tile.show()
        self._main_layout.insertWidget(0, self._rule_bar_tile)
        self._rule_bar_tile._current_position = "top"
        self._rule_bar_tile.position_changed.emit("top")
        
    def _move_rule_bar_between(self):
        """Move rule bar between grid and rule panel (inside splitter)."""
        # Only move if not already in between position
        if getattr(self._rule_bar_tile, '_current_position', None) == "between":
            return
            
        # Hide and reparent
        self._rule_bar_tile.hide()
        self._rule_bar_tile.setParent(None)
        
        # Remove from main layout
        self._main_layout.removeWidget(self._rule_bar_tile)
        
        # Get current widget at index 1 (lower tabs)
        lower_widget = self._splitter.widget(1)
        
        # Show and insert rule bar at index 1, which pushes lower_widget to index 2
        self._rule_bar_tile.show()
        self._splitter.insertWidget(1, self._rule_bar_tile)
        
        # Use natural sizing like the default position
        self._rule_bar_tile.setMinimumHeight(0)
        self._rule_bar_tile.setMaximumHeight(16777215)
        
        # Set stretch factors - rule bar gets 0 stretch (fixed size)
        self._splitter.setStretchFactor(0, 4)  # Grid expands
        self._splitter.setStretchFactor(1, 0)  # Rule bar fixed
        if lower_widget:
            self._splitter.setStretchFactor(2, 1)  # Lower tabs expand
        
        # Set minimum height for rule bar, allow expansion for multi-line
        # Base: margins (4+4) + input (20) + padding = ~30px
        self._rule_bar_tile.setMinimumHeight(30)
        self._rule_bar_tile.setMaximumHeight(16777215)
        
        self._rule_bar_tile._current_position = "between"
        self._rule_bar_tile.position_changed.emit("between")
        
    def _move_rule_bar_to_bottom(self):
        """Move rule bar below the rule panel (after splitter)."""
        # Only move if not already at bottom
        if getattr(self._rule_bar_tile, '_current_position', None) == "bottom":
            return
            
        # Hide and reparent (QSplitter doesn't have removeWidget)
        self._rule_bar_tile.hide()
        self._rule_bar_tile.setParent(None)
        
        # Remove from main layout if present  
        self._main_layout.removeWidget(self._rule_bar_tile)
        
        # Set minimum height for consistency, allow expansion for multi-line
        # Base: margins (4+4) + input (20) + padding = ~30px
        self._rule_bar_tile.setMinimumHeight(30)
        self._rule_bar_tile.setMaximumHeight(16777215)
        
        # Show and insert after splitter in main layout
        # The splitter is at index 0 (or 1 if rule bar was at top), so insert at count
        self._rule_bar_tile.show()
        self._main_layout.addWidget(self._rule_bar_tile)
        self._rule_bar_tile._current_position = "bottom"
        self._rule_bar_tile.position_changed.emit("bottom")
        
    def _is_rule_bar_drag(self, event) -> bool:
        """Check if drag event is from the rule bar."""
        mime = event.mimeData()
        return mime is not None and mime.hasText() and mime.text() == "rule_bar"
        
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        """Accept drags from the rule bar."""
        if self._is_rule_bar_drag(event):
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
        """Handle drag movement - only show indicators, don't move yet."""
        if not self._is_rule_bar_drag(event):
            return
            
        # Get mouse position relative to this widget
        pos = event.position().toPoint().y()
        
        # Get geometry of key widgets
        splitter_geo = self._splitter.geometry()
        splitter_y = splitter_geo.y()
        splitter_bottom = splitter_y + splitter_geo.height()
        workspace_height = self.height()
        
        # Calculate zones
        top_threshold = splitter_y + 60
        bottom_threshold = splitter_bottom - 200
        
        # Only show indicators, don't move the widget yet
        self._hide_all_drop_indicators()
        
        if pos < top_threshold:
            self._show_drop_indicator(self._drop_indicator_top, 0)
            self._drop_target = "top"
        elif pos < bottom_threshold:
            # Position between indicator exactly at bottom of grid widget
            # The grid is at index 0 in the splitter
            grid_widget = self._splitter.widget(0)
            if grid_widget:
                grid_bottom = grid_widget.geometry().y() + grid_widget.geometry().height()
                between_y = splitter_y + grid_bottom
            else:
                # Fallback to 60% if can't determine grid size
                between_y = int(splitter_y + (splitter_bottom - splitter_y) * 0.6)
            self._show_drop_indicator(self._drop_indicator_between, between_y)
            self._drop_target = "between"
        else:
            self._show_drop_indicator(self._drop_indicator_bottom, splitter_bottom - 3)
            self._drop_target = "bottom"
            
        event.acceptProposedAction()
        
    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent):
        """Hide indicators when drag leaves."""
        self._hide_all_drop_indicators()
        self._drop_target = None
        
    def dropEvent(self, event: QtGui.QDropEvent):
        """Handle drop - actually move the rule bar now."""
        self._hide_all_drop_indicators()
        if self._is_rule_bar_drag(event):
            target = getattr(self, '_drop_target', None)
            if target == "top":
                self._move_rule_bar_to_top()
            elif target == "between":
                self._move_rule_bar_between()
            elif target == "bottom":
                self._move_rule_bar_to_bottom()
            self._drop_target = None
            event.acceptProposedAction()

    @property
    def name_box(self) -> QtWidgets.QLabel:
        return self._rule_bar_tile.get_name_box()

    @property
    def rule_bar(self):
        return self._rule_bar_tile

    @property
    def tabs(self) -> QtWidgets.QTabWidget:
        return self._tabs

    @property
    def rule_panel(self) -> RulePanel:
        return self._rule_panel

    @property
    def flow_panel(self) -> CalculationFlowPanel:
        return self._flow_panel

    @property
    def circular_refs_panel(self) -> CircularReferencesPanel:
        return self._circular_refs_panel

    @property
    def lower_tabs(self) -> QtWidgets.QTabWidget:
        return self._lower_tabs

    @property
    def splitter(self) -> QtWidgets.QSplitter:
        return self._splitter
