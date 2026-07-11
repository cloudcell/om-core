"""Owner-key factories for StatusManager.

Centralizing these strings prevents typo-created immortal owners and makes
it easy to see every lifecycle that can affect the status bar.
"""
from __future__ import annotations


class StatusOwner:
    """Namespace of owner-key factories."""

    @staticmethod
    def engine() -> str:
        return "engine"

    @staticmethod
    def recalc(correlation_id: str) -> str:
        return f"recalc:{correlation_id}"

    @staticmethod
    def ui_refresh() -> str:
        return "ui_refresh"

    @staticmethod
    def load(correlation_id: str) -> str:
        return f"load:{correlation_id}"

    @staticmethod
    def save(correlation_id: str) -> str:
        return f"save:{correlation_id}"

    @staticmethod
    def visible_refresh(view_id: str) -> str:
        return f"visible_refresh:{view_id}"

    @staticmethod
    def error_tracker() -> str:
        return "error_tracker"
