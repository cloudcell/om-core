"""Render helpers for the monitor overlay left/right panes."""

from __future__ import annotations

from datetime import datetime

from .state import MonitorState


def render_topics_text(state: MonitorState) -> str:
    """Render the topic checklist as a plain text string for BufferControl."""
    lines: list[str] = []
    topics = state.get_topics()
    cursor = state.cursor

    # [All] row
    all_checked = "✓" if state.are_all_enabled() else " "
    prefix = ">" if cursor == 0 else " "
    lines.append(f"{prefix}[{all_checked}] [All]")

    for i, topic in enumerate(topics):
        row = i + 1
        checked = "✓" if state.is_enabled(topic) else " "
        prefix = ">" if row == cursor else " "
        lines.append(f"{prefix}[{checked}] {topic}")

    return "\n".join(lines)


def render_log_text(state: MonitorState) -> str:
    """Render the filtered message log as a plain text string for BufferControl.

    Long lines are word-wrapped; continuation lines are padded so the
    payload text aligns underneath the first line's payload column.
    """
    import os
    import textwrap

    lines: list[str] = []
    try:
        cols, _ = os.get_terminal_size()
        width = max(40, cols - state.left_width - 4)
    except Exception:
        width = 80

    for ts, topic, text in state.get_filtered_messages():
        prefix = f"{ts} "
        prefix_len = len(prefix)

        if len(prefix) + len(text) <= width:
            lines.append(prefix + text)
            continue

        # Wrap payload text alone so continuation lines fit after indent
        wrapped = textwrap.wrap(text, width=width - prefix_len, break_long_words=True)
        if not wrapped:
            lines.append(prefix + text)
            continue

        indent = " " * prefix_len
        lines.append(prefix + wrapped[0])
        for wline in wrapped[1:]:
            lines.append(indent + wline)

    return "\n".join(lines)


def format_message(topic: str, payload: object) -> tuple[str, str]:
    """Format a bus message into a compact preview string.

    Returns (timestamp, display_text).
    """
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    payload_str = str(payload)
    return ts, f"{topic} → {payload_str}"
