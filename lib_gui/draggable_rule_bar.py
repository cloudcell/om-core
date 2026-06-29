"""Draggable tile-style rule bar with braille drag handle."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtSvg import QSvgRenderer


class RuleSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    """Syntax highlighter for OpenM rules with colored text."""
    
    def __init__(self, document):
        super().__init__(document)
        self._setup_formats()
        
    def _setup_formats(self):
        """Set up color formats for different token types."""
        # Operators (=, +, -, *, /, etc.)
        self._operator_format = QtGui.QTextCharFormat()
        self._operator_format.setForeground(QtGui.QColor("#D73A49"))  # Red
        
        # Numbers
        self._number_format = QtGui.QTextCharFormat()
        self._number_format.setForeground(QtGui.QColor("#005CC5"))  # Blue
        
        # Strings (quoted)
        self._string_format = QtGui.QTextCharFormat()
        self._string_format.setForeground(QtGui.QColor("#22863A"))  # Green
        
        # Keywords (PREV, NEXT, FIRST, LAST, THIS, etc.)
        self._keyword_format = QtGui.QTextCharFormat()
        self._keyword_format.setForeground(QtGui.QColor("#6F42C1"))  # Purple
        
        # Dimension references (Dim.Item)
        self._dimension_format = QtGui.QTextCharFormat()
        self._dimension_format.setForeground(QtGui.QColor("#E36209"))  # Orange
        
        # Functions (IF, SUM, AVG, etc.)
        self._function_format = QtGui.QTextCharFormat()
        self._function_format.setForeground(QtGui.QColor("#6F42C1"))  # Purple
        
    def highlightBlock(self, text: str):
        """Apply syntax highlighting to a block of text."""
        import re
        
        # Highlight operators
        for match in re.finditer(r'[=+\-*/()<>,:;]', text):
            self.setFormat(match.start(), match.end() - match.start(), self._operator_format)
        
        # Highlight numbers (integers and floats)
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self._number_format)
        
        # Highlight strings (single and double quoted)
        for match in re.finditer(r'["\'][^"\']*["\']', text):
            self.setFormat(match.start(), match.end() - match.start(), self._string_format)
        
        # Highlight keywords
        keywords = ['PREV', 'NEXT', 'FIRST', 'LAST', 'THIS', 'IF', 'THEN', 'ELSE', 'AND', 'OR', 'NOT']
        for keyword in keywords:
            for match in re.finditer(r'\b' + keyword + r'\b', text, re.IGNORECASE):
                self.setFormat(match.start(), len(keyword), self._keyword_format)
        
        # Highlight dimension references (Dim.Item pattern)
        for match in re.finditer(r'\b[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self._dimension_format)
        
        # Highlight function calls (name followed by parenthesis)
        for match in re.finditer(r'\b[A-Za-z][A-Za-z0-9_]*\s*(?=\()', text):
            self.setFormat(match.start(), match.end() - match.start(), self._function_format)


class DraggableRuleBar(QtWidgets.QFrame):
    """
    A draggable tile-style rule bar with braille drag handle.
    
    Features:
    - Braille drag handle (⣿ - 8 dots) on the left
    - Draggable between top and bottom positions
    - Clean tile appearance without window chrome
    """
    
    position_changed = QtCore.Signal(str)  # "top", "between", or "bottom"
    returnPressed = QtCore.Signal()  # Emitted when Enter is pressed (for rule submission)
    textChanged = QtCore.Signal()  # Proxied from QTextEdit for QLineEdit compatibility
    
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        
        self._drag_start_pos: QtCore.QPoint | None = None
        self._current_position = "top"  # "top", "between", "bottom"
        
        self._setup_ui()
        self._setup_dragging()
        
    def _setup_ui(self):
        """Set up the tile-style UI."""
        self.setStyleSheet("""
            DraggableRuleBar {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
            }
            DraggableRuleBar:hover {
                border: 1px solid #9CA3AF;
            }
        """)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # Braille drag handle (⣿ - 8 dots: 2 rows x 4 dots)
        self._drag_handle = QtWidgets.QLabel("⣿")
        self._drag_handle.setStyleSheet("""
            color: #9CA3AF;
            font-size: 14px;
            padding: 1px 2px;
        """)
        self._drag_handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self._drag_handle.setToolTip("Drag to reposition")
        layout.addWidget(self._drag_handle)
        
        # Name/address label
        self._name_box = QtWidgets.QLabel()
        self._name_box.setMinimumWidth(130)
        self._name_box.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        self._name_box.setStyleSheet("color: #374151; font-size: 13px;")
        layout.addWidget(self._name_box)
        
        # Rule input with overlay clear button
        input_container = QtWidgets.QWidget()
        input_container.setMinimumHeight(20)
        
        # Rule input (multi-line QPlainTextEdit with syntax highlighting)
        self._rule_input = QtWidgets.QPlainTextEdit(input_container)
        self._rule_input.setPlaceholderText("Rule: Dim.Item = expr  |  Cell: =expr")
        self._rule_input.setStyleSheet("""
            QPlainTextEdit {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 0px 70px 0px 8px;
                font-family: monospace;
                font-size: 13px;
            }
            QPlainTextEdit:focus {
                background-color: white;
                border-color: #3B82F6;
            }
        """)
        # Set initial height based on font metrics
        fm = QtGui.QFontMetrics(self._rule_input.font())
        # Use ascent + descent for more accurate line height calculation
        line_height = fm.ascent() + fm.descent()
        self._rule_input.setFixedHeight(line_height + 8)  # line + border (2) + breathing room (6)
        self._rule_input.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._rule_input.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Handle Alt+Enter for new lines, Enter for submit
        self._rule_input.installEventFilter(self)
        
        # Set up syntax highlighter for colored rules
        self._highlighter = RuleSyntaxHighlighter(self._rule_input.document())
        
        # Proxy QPlainTextEdit textChanged to rule bar's textChanged signal
        self._rule_input.textChanged.connect(self.textChanged.emit)
        # Also adjust height when text changes
        self._rule_input.textChanged.connect(self._adjust_input_height)
        # Check blinking when text changes
        self._rule_input.textChanged.connect(self._update_blink_state)
        
        # Clear button overlay (positioned on top of input, no background)
        self._clear_btn = QtWidgets.QPushButton(input_container)
        self._clear_btn.setFixedSize(28, 24)
        self._clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setGeometry(input_container.width() - 62, 0, 28, 24)
        
        # Load tabler backspace outline icon - 2x larger (24px)
        backspace_icon = self._load_svg_icon("backspace", size=24)
        if not backspace_icon.isNull():
            self._clear_btn.setIcon(QtGui.QIcon(backspace_icon))
            self._clear_btn.setIconSize(QtCore.QSize(24, 24))
            # Apply grey color effect to icon
            color_effect = QtWidgets.QGraphicsColorizeEffect(self._clear_btn)
            color_effect.setColor(QtGui.QColor("#D1D5DB"))
            self._clear_btn.setGraphicsEffect(color_effect)
        else:
            self._clear_btn.setText("×")
            self._clear_btn.setStyleSheet("font-size: 20px; color: #9CA3AF;")
        
        # Transparent button - light grey icon
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #D1D5DB;
                padding: 0;
            }
            QPushButton:hover {
                color: #9CA3AF;
            }
            QPushButton:pressed {
                color: #6B7280;
            }
        """)
        self._clear_btn.clicked.connect(self._rule_input.clear)
        
        # Expand/collapse toggle button (positioned after clear button)
        self._expand_btn = QtWidgets.QPushButton(input_container)
        self._expand_btn.setFixedSize(24, 20)
        self._expand_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setGeometry(input_container.width() - 26, 2, 24, 20)
        self._expand_btn.setToolTip("Expand rule bar")
        
        # Track expanded state
        self._is_expanded = False
        
        # Blink timer for overflow indicator
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_on = False
        
        # Load expand icon (arrow-big-down-lines)
        expand_icon = self._load_svg_icon("arrow-big-down-lines", size=20)
        if not expand_icon.isNull():
            self._expand_btn.setIcon(QtGui.QIcon(expand_icon))
            self._expand_btn.setIconSize(QtCore.QSize(20, 20))
            color_effect = QtWidgets.QGraphicsColorizeEffect(self._expand_btn)
            color_effect.setColor(QtGui.QColor("#9CA3AF"))
            self._expand_btn.setGraphicsEffect(color_effect)
        else:
            self._expand_btn.setText("▼")
        
        self._expand_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self._expand_btn.clicked.connect(self._toggle_expand)
        
        # Update button position when container resizes
        def update_input_geometry(e):
            h = self._rule_input.height()
            self._rule_input.setGeometry(0, 0, e.size().width(), h)
            # Keep buttons at fixed height, vertically centered
            self._clear_btn.setGeometry(e.size().width() - 62, (h - 24) // 2, 28, 24)
            self._expand_btn.setGeometry(e.size().width() - 26, (h - 20) // 2, 24, 20)
            input_container.setFixedHeight(h)
        
        input_container.resizeEvent = update_input_geometry
        
        layout.addWidget(input_container, 1)
        
    def _setup_dragging(self):
        """Set up drag behavior."""
        self._drag_handle.setMouseTracking(True)
        
    def eventFilter(self, obj, event):
        """Handle Alt+Enter to insert new lines."""
        if obj == self._rule_input and event.type() == QtCore.QEvent.Type.KeyPress:
            # Alt+Enter inserts a new line
            if event.key() == QtCore.Qt.Key.Key_Return or event.key() == QtCore.Qt.Key.Key_Enter:
                if event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier:
                    # Insert new line
                    cursor = self._rule_input.textCursor()
                    cursor.insertText("\n")
                    self._rule_input.setTextCursor(cursor)
                    # Expand height based on line count
                    self._adjust_input_height()
                    return True
                else:
                    # Regular Enter - emit returnPressed signal for rule submission
                    self.returnPressed.emit()
                    return True
        return super().eventFilter(obj, event)
        
    def _adjust_input_height(self):
        """Set height to one of two fixed states: collapsed or expanded."""
        # Get font metrics to calculate exact line height
        fm = QtGui.QFontMetrics(self._rule_input.font())
        # Use ascent + descent for more accurate line height
        line_height = fm.ascent() + fm.descent()
        
        # Count actual lines in the document
        block_count = self._rule_input.blockCount()
        
        # Border (2) + breathing room (6)
        extra = 8
        
        if self._is_expanded:
            # Expanded: show all lines up to 6 lines max
            max_lines = 6
            display_lines = min(block_count, max_lines)
            new_height = (display_lines * line_height) + extra
            self._rule_input.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            # Collapsed: show exactly 1 line, hide scrollbar
            new_height = line_height + extra
            self._rule_input.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self._rule_input.setFixedHeight(new_height)
        self._rule_input.parent().setFixedHeight(new_height)
        self.setFixedHeight(new_height + 8)
        
    def _toggle_expand(self):
        """Toggle between expanded and collapsed state."""
        self._is_expanded = not self._is_expanded
        self._adjust_input_height()
        
        # Refresh parent layout to redistribute space
        parent = self.parent()
        if parent:
            parent.adjustSize()
            # If we're in a splitter, refresh its sizes
            grandparent = parent.parent()
            if grandparent and hasattr(grandparent, 'sizes'):
                grandparent.update()
        
        # Stop blinking when expanded
        self._blink_timer.stop()
        
        # Update icon based on state
        if self._is_expanded:
            self._expand_btn.setToolTip("Collapse rule bar")
            self._set_expand_btn_color("#9CA3AF")
            collapse_icon = self._load_svg_icon("arrow-big-up-line", size=24)
            if not collapse_icon.isNull():
                self._expand_btn.setIcon(QtGui.QIcon(collapse_icon))
            else:
                self._expand_btn.setText("▲")
        else:
            self._expand_btn.setToolTip("Expand rule bar (more content available)")
            # Check if we need to blink based on scrollbar visibility
            scrollbar = self._rule_input.verticalScrollBar()
            if scrollbar.isVisible():
                if not self._blink_timer.isActive():
                    self._blink_timer.start(500)
            else:
                self._blink_timer.stop()
                self._set_expand_btn_color("#9CA3AF")
            expand_icon = self._load_svg_icon("arrow-big-down-lines", size=24)
            if not expand_icon.isNull():
                self._expand_btn.setIcon(QtGui.QIcon(expand_icon))
            else:
                self._expand_btn.setText("▼")
        
    def _toggle_blink(self):
        """Toggle blink state for expand button."""
        self._blink_on = not self._blink_on
        if self._blink_on:
            self._set_expand_btn_color("#EF4444")  # Red when blinking on
        else:
            self._set_expand_btn_color("#9CA3AF")  # Gray when blinking off
    
    def _update_blink_state(self):
        """Update blinking based on content overflow when collapsed."""
        if not self._is_expanded:
            # Check if content overflows (more than 1 line of text)
            doc_height = self._rule_input.document().size().height()
            viewport_height = self._rule_input.viewport().height()
            has_overflow = doc_height > viewport_height + 2  # Small tolerance
            
            if has_overflow:
                if not self._blink_timer.isActive():
                    self._blink_timer.start(500)
            else:
                self._blink_timer.stop()
                self._set_expand_btn_color("#9CA3AF")
    
    def _set_expand_btn_color(self, color: str):
        """Set the color of the expand button icon."""
        color_effect = QtWidgets.QGraphicsColorizeEffect(self._expand_btn)
        color_effect.setColor(QtGui.QColor(color))
        self._expand_btn.setGraphicsEffect(color_effect)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Start drag if clicking on handle."""
        if self._drag_handle.geometry().contains(event.position().toPoint()):
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_handle.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Handle drag movement."""
        if self._drag_start_pos is not None:
            # Calculate drag distance
            current_pos = event.globalPosition().toPoint()
            distance = (current_pos - self._drag_start_pos).manhattanLength()
            
            if distance > QtWidgets.QApplication.startDragDistance():
                # Start drag operation
                drag = QtGui.QDrag(self)
                mime_data = QtCore.QMimeData()
                mime_data.setText("rule_bar")
                drag.setMimeData(mime_data)
                
                # Create drag pixmap
                pixmap = self.grab()
                drag.setPixmap(pixmap)
                drag.setHotSpot(event.position().toPoint())
                
                self._drag_handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
                self._drag_start_pos = None
                
                drag.exec(QtCore.Qt.DropAction.MoveAction)
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """End drag."""
        self._drag_handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
        
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        """Ignore drag enter events so parent handles the drop."""
        event.ignore()
            
    def get_name_box(self) -> QtWidgets.QLabel:
        """Get the name/address label."""
        return self._name_box
        
    def get_rule_input(self) -> QtWidgets.QTextEdit:
        """Get the rule input field."""
        return self._rule_input
        
    def text(self) -> str:
        """Get the rule text (QLineEdit compatibility)."""
        return self._rule_input.toPlainText()
        
    def setText(self, text: str) -> None:
        """Set the rule text (QLineEdit compatibility)."""
        self._rule_input.setPlainText(text)
        self._adjust_input_height()  # Reset height for new content
        self._update_blink_state()   # Update blinking based on overflow
        
    def get_rule_input(self) -> QtWidgets.QPlainTextEdit:
        """Get the rule input field."""
        return self._rule_input
        
    def setPlaceholderText(self, text: str) -> None:
        """Set placeholder text (QLineEdit compatibility)."""
        self._rule_input.setPlaceholderText(text)
        
    def setEnabled(self, enabled: bool) -> None:
        """Set enabled state (proxy to internal widgets)."""
        super().setEnabled(enabled)
        self._rule_input.setEnabled(enabled)
        
    def _load_svg_icon(self, icon_name: str, size: int = 18) -> QtGui.QPixmap:
        """Load a Tabler SVG icon and render it to a pixmap."""
        try:
            # Use tabler filled icons
            icon_path = Path(__file__).parent.parent / "assets" / "icons" / "tabler" / "icons" / "filled" / f"{icon_name}.svg"
            if not icon_path.exists():
                # Fallback to outline
                icon_path = Path(__file__).parent.parent / "assets" / "icons" / "tabler" / "icons" / "outline" / f"{icon_name}.svg"
            if not icon_path.exists():
                return QtGui.QPixmap()
            renderer = QSvgRenderer(str(icon_path))
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
            painter.end()
            return pixmap
        except Exception:
            return QtGui.QPixmap()
