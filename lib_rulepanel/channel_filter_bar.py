"""Channel filter bar widget for rule panel."""
from __future__ import annotations

from typing import List, Set

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt, Signal

from .channel_pill import ChannelPill
from .rule_models import ChannelMetrics


class ChannelFilterBar(QWidget):
    """
    Horizontal bar of channel filter pills for rule filtering.
    """
    
    filter_changed = Signal(set)  # Emit selected channels (Set[str])
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pills: List[ChannelPill] = []
        self.selected_channels: Set[str] = set()
        self.channel_data: List[ChannelMetrics] = []
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the pill bar layout."""
        layout = QHBoxLayout(self)
        layout.setSpacing(1)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.setLayout(layout)
        self.setStyleSheet("background-color: #FAFAFA;")
        
    def set_channel_data(self, channel_data: List[ChannelMetrics]):
        """Set channel data and create pills."""
        self.channel_data = channel_data
        self.create_pills()
        
    def create_pills(self):
        """Create pill widgets from data."""
        layout = self.layout()
        
        # Clear existing
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.pills = []
        
        for data in self.channel_data:
            pill = ChannelPill(data)
            pill.clicked_channel.connect(self.on_pill_clicked)
            pill.multi_select_requested.connect(lambda ch=data.channel_id: self.on_pill_clicked(ch, True))
            layout.addWidget(pill)
            self.pills.append(pill)
            
        # Add stretch to keep pills left-aligned
        layout.addStretch()
        
    def on_pill_clicked(self, channel_id: str, multi_select: bool = False):
        """Handle pill click - toggle selection with optional multi-select."""
        if multi_select:
            # Ctrl+click: toggle this channel in multi-selection
            if channel_id in self.selected_channels:
                self.selected_channels.remove(channel_id)
            else:
                self.selected_channels.add(channel_id)
        else:
            # Normal click: single select
            if channel_id in self.selected_channels and len(self.selected_channels) == 1:
                # Clicking the only selected pill deselects it
                self.selected_channels.clear()
            else:
                self.selected_channels = {channel_id}
            
        self.update_pill_states()
        self.filter_changed.emit(self.selected_channels)
        
    def update_pill_states(self):
        """Update all pills to match current selection."""
        for pill in self.pills:
            pill.is_selected = pill.data.channel_id in self.selected_channels
            pill.update_style()
            pill.update()
            
    def clear_selection(self):
        """Clear all filters."""
        self.selected_channels.clear()
        self.update_pill_states()
        self.filter_changed.emit(self.selected_channels)

    def setEnabled(self, enabled: bool):
        """Enable or disable all pills."""
        super().setEnabled(enabled)
        for pill in self.pills:
            pill.setEnabled(enabled)
            # Update visual state to show disabled
            if not enabled:
                pill.setStyleSheet(pill.styleSheet() + "QPushButton { color: #9CA3AF; }")
            else:
                pill.update_style()
                
    def select_channels(self, channels: Set[str]):
        """Programmatically select channels."""
        self.selected_channels = set(channels)
        self.update_pill_states()
        self.filter_changed.emit(self.selected_channels)
        
    def get_selected_channels(self) -> Set[str]:
        """Get currently selected channels."""
        return self.selected_channels.copy()
