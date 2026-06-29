"""Channel filter pill widget for rule panel."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QFont, QFontMetrics
from PySide6.QtSvg import QSvgRenderer

if TYPE_CHECKING:
    from .rule_models import ChannelMetrics


def _get_icon_path(channel_id: str) -> Path:
    """Get icon path for a channel ID."""
    # Map channel IDs to lucide icon names
    icon_map = {
        "@.value": "calculator",
        "@.fill": "palette",
        "@.format_number": "hash",
        "@.format_text": "type",
        "@.format_null": "circle",
        "@.format_error": "alert-circle",
        "@.font_family": "type",
        "@.font_size": "text",
        "@.font_weight": "bold",
        "@.font_italic": "italic",
        "@.font_color": "palette",
        "@.text_h_align": "align-left",
        "@.text_v_align": "align-vertical",
        "@.text_indent": "indent",
        "@.text_wrap": "wrap-text",
        "@.comment": "message-square",
    }
    
    icon_name = icon_map.get(channel_id, "circle")
    # Project-relative path - will be resolved by caller
    return Path("assets/icons/lucide/icons") / f"{icon_name}.svg"


class ChannelPill(QPushButton):
    """
    A single channel filter pill for the filter bar.
    Shows: icon + count + status dot + mini sparkline
    """
    
    clicked_channel = Signal(str)
    multi_select_requested = Signal(str)
    
    # Size constants - compact
    PILL_HEIGHT = 24
    ICON_SIZE = 12
    COUNT_FONT_SIZE = 9
    SPARKLINE_WIDTH = 16
    
    def __init__(self, channel_data: "ChannelMetrics", parent=None):
        super().__init__(parent)
        self.data = channel_data
        self.is_selected = False
        self.is_hovered = False
        
        self.setup_ui()
        self.load_icon()
        
        # Tooltip with full info
        self.setToolTip(f"{self.data.channel_id.replace('@.', '')}: {self.data.count} rules")
        
    def setup_ui(self):
        """Configure the pill appearance."""
        self.setFixedHeight(self.PILL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        
        # Calculate width based on content
        self.update_size()
        
        # Styling
        self.update_style()
        
        # Focus policy for keyboard nav
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        
    def load_icon(self):
        """Load SVG icon and render to pixmap."""
        try:
            from assets.icons.icon_mapping import get_icon_path
            icon_path = get_icon_path(self.data.channel_id)
            self.renderer = QSvgRenderer(str(icon_path))
            self.icon_pixmap = QPixmap(self.ICON_SIZE, self.ICON_SIZE)
            self.icon_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(self.icon_pixmap)
            self.renderer.render(painter)
            painter.end()
        except Exception as e:
            print(f"Failed to load icon for {self.data.channel_id}: {e}")
            self.icon_pixmap = None
            
    def update_size(self):
        """Calculate and set appropriate width."""
        # Base width: padding + icon + spacing + count + sparkline + padding
        base_width = 8 + self.ICON_SIZE + 4 + 16 + 4 + self.SPARKLINE_WIDTH + 8
        self.setFixedWidth(max(base_width, 50))
        
    def update_style(self):
        """Update stylesheet based on state."""
        if self.is_selected:
            # Active state - filled blue
            self.setStyleSheet("""
                QPushButton {
                    background-color: #DBEAFE;
                    border: 1px solid #3B82F6;
                    border-radius: 10px;
                    padding: 4px 8px;
                    color: #1E40AF;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #BFDBFE;
                    border-color: #2563EB;
                }
            """)
        elif self.data.count == 0:
            # Empty state - dashed, muted
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: 1px dashed #D1D5DB;
                    border-radius: 10px;
                    padding: 4px 8px;
                    color: #9CA3AF;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                    border-style: solid;
                    color: #6B7280;
                }
            """)
        else:
            # Default state
            self.setStyleSheet("""
                QPushButton {
                    background-color: #F3F4F6;
                    border: 1px solid #E5E7EB;
                    border-radius: 10px;
                    padding: 4px 8px;
                    color: #374151;
                }
                QPushButton:hover {
                    background-color: #FFFFFF;
                    border-color: #D1D5DB;
                }
            """)
            
    def paintEvent(self, event):
        """Custom paint to draw icon, count, and sparkline."""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        x_offset = 8
        y_center = self.height() // 2
        
        # Draw icon
        if self.icon_pixmap:
            icon_y = y_center - self.ICON_SIZE // 2
            painter.drawPixmap(x_offset, icon_y, self.icon_pixmap)
        
        x_offset += self.ICON_SIZE + 4
        
        # Draw count
        count_str = str(self.data.count) if self.data.count < 100 else "⁺"
        font = QFont("Inter", self.COUNT_FONT_SIZE)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        
        # Color based on state
        if self.is_selected:
            painter.setPen(QColor("#1E40AF"))
        elif self.data.count == 0:
            painter.setPen(QColor("#9CA3AF"))
        else:
            painter.setPen(QColor("#374151"))
            
        count_y = y_center + 3  # Slight offset for visual center
        painter.drawText(x_offset, count_y, count_str)
        
        # Draw status dot if context matches
        if self.data.context_matches > 0:
            dot_color = QColor("#3B82F6") if self.is_selected else QColor("#10B981")
            painter.setBrush(dot_color)
            painter.setPen(Qt.PenStyle.NoPen)
            dot_x = x_offset + 12
            dot_y = y_center - 6
            painter.drawEllipse(dot_x, dot_y, 4, 4)
        
        x_offset += 16 + 4
        
        # Draw sparkline
        self.draw_sparkline(painter, x_offset, y_center - 4)
        
        painter.end()
        
    def draw_sparkline(self, painter: QPainter, x: int, y: int):
        """Draw 5-bar sparkline showing rule distribution."""
        bar_width = 3
        bar_height = 8
        gap = 1
        
        # Calculate fill levels based on count relative to max (20 for demo)
        max_count = 20
        fill_ratio = min(self.data.count / max_count, 1.0)
        
        # Create 5 segments with varied fill
        segments = []
        for i in range(5):
            # Create visual variation
            segment_fill = max(0, min(1, fill_ratio * (1.2 - i * 0.15)))
            segments.append(segment_fill)
        
        for i, fill in enumerate(segments):
            bar_x = x + i * (bar_width + gap)
            
            if fill > 0.6:
                color = QColor("#3B82F6") if self.is_selected else QColor("#6B7280")
            elif fill > 0.3:
                color = QColor("#93C5FD") if self.is_selected else QColor("#9CA3AF")
            elif fill > 0:
                color = QColor("#BFDBFE") if self.is_selected else QColor("#D1D5DB")
            else:
                color = QColor("#E5E7EB")
                
            painter.fillRect(bar_x, y, bar_width, bar_height, color)
            
    def mousePressEvent(self, event):
        """Handle click with press animation and multi-select."""
        # Check for Ctrl key
        ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        
        # Bouncy press effect
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(100)
        self.animation.setEasingCurve(QEasingCurve.Type.OutBack)
        
        geo = self.geometry()
        self.animation.setStartValue(geo)
        self.animation.setEndValue(geo)
        
        self.animation.start()
        
        super().mousePressEvent(event)
        
        if ctrl_pressed:
            self.multi_select_requested.emit(self.data.channel_id)
        else:
            self.clicked_channel.emit(self.data.channel_id)
