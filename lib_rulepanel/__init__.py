"""Rule panel library for OpenM.

This library provides widgets for displaying and editing rules with:
- Channel filter pills for filtering by @ dimension (value, fill, format, etc.)
- Editable rule rows with drag-drop reordering
- Rule list with selection and inline editing

Example:
    from lib_rulepanel import ChannelFilterBar, RuleListWidget, RuleData

    # Create filter bar with channel data
    pill_bar = ChannelFilterBar()
    pill_bar.set_channel_data([
        ChannelMetrics("@.value", "calculator", 12, 1, 3),
        ChannelMetrics("@.fill", "palette", 5, 0, 2),
    ])
    pill_bar.filter_changed.connect(on_filter_changed)

    # Create rule list with rules
    rule_list = RuleListWidget()
    rule_list.set_rules([
        RuleData("PL.Revenue", "Price * Quantity", "@.value"),
        RuleData("PL.Cost", "Qty * UnitCost", "@.value"),
    ])
    rule_list.rule_edited.connect(on_rule_edited)
"""

from __future__ import annotations

# Public API exports
from .channel_pill import ChannelPill
from .channel_filter_bar import ChannelFilterBar
from .rule_models import RuleData, ChannelMetrics
from .rule_row import RuleRow, EditableRuleRow
from .rule_list import RuleListWidget

# Re-export for backward compatibility
ChannelData = ChannelMetrics

__all__ = [
    # Channel filtering
    "ChannelPill",
    "ChannelData",  # Deprecated: use ChannelMetrics
    "ChannelMetrics",
    "ChannelFilterBar",
    # Rule data models
    "RuleData",
    # Rule display/editing
    "RuleRow",
    "EditableRuleRow",
    "RuleListWidget",
]
