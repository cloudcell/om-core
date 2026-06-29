"""Monitor state — topic collection, message buffer, and toggle tracking."""

from __future__ import annotations

from collections import deque
from typing import Callable

from .. import config as cfg


class MonitorState:
    """Bounded topic/message store for the bus monitor overlay."""

    def __init__(self) -> None:
        self._topics: set[str] = set()
        self._topic_enabled: dict[str, bool] = {}
        self._topic_cursor: int = 0
        self._monitor_messages: deque[tuple[str, str, str]] = deque(
            maxlen=cfg.MAX_MONITOR_MESSAGES
        )
        self._on_change: Callable[[], None] | None = None
        self._left_width: int = 40

    # ------------------------------------------------------------------
    # Topic management
    # ------------------------------------------------------------------

    def set_change_callback(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    @staticmethod
    def _normalize_topic(topic: str) -> str:
        if topic.startswith("reply.command."):
            return "reply.command.*"
        if topic.startswith("reply.query."):
            return "reply.query.*"
        return topic

    def add_topic(self, topic: str) -> None:
        """Register a new topic. Auto-enable it by default."""
        topic = self._normalize_topic(topic)
        if topic in self._topics:
            return
        self._topics.add(topic)
        self._topic_enabled[topic] = True
        self._maybe_evict_oldest_topic()

    def _maybe_evict_oldest_topic(self) -> None:
        """Evict the oldest-seen topic if we exceed MAX_MONITOR_TOPICS."""
        if len(self._topics) <= cfg.MAX_MONITOR_TOPICS:
            return
        # Evict the topic that was added earliest (FIFO from _monitor_messages)
        # We approximate by finding the topic with the oldest first occurrence.
        oldest_topic: str | None = None
        oldest_time: float = float("inf")
        for ts, topic, _ in self._monitor_messages:
            if topic in self._topics:
                # ts is HH:MM:SS string; we can't sort by it perfectly without
                # storing a real timestamp. Use deque order instead: the first
                # message in the deque is the oldest.
                oldest_topic = topic
                break
        if oldest_topic and len(self._topics) > cfg.MAX_MONITOR_TOPICS:
            self._topics.discard(oldest_topic)
            self._topic_enabled.pop(oldest_topic, None)

    def toggle_topic(self, topic: str) -> None:
        self._topic_enabled[topic] = not self._topic_enabled.get(topic, True)
        self._notify()

    def enable_all(self) -> None:
        for t in self._topics:
            self._topic_enabled[t] = True
        self._notify()

    def disable_all(self) -> None:
        for t in self._topics:
            self._topic_enabled[t] = False
        self._notify()

    def are_all_enabled(self) -> bool:
        if not self._topics:
            return True
        return all(self._topic_enabled.get(t, True) for t in self._topics)

    # ------------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------------

    @property
    def cursor(self) -> int:
        return self._topic_cursor

    @cursor.setter
    def cursor(self, value: int) -> None:
        count = len(self._topics)
        if count == 0:
            self._topic_cursor = 0
            return
        self._topic_cursor = max(0, min(value, count))
        self._notify()

    def cursor_up(self) -> None:
        self.cursor = self._topic_cursor - 1

    def cursor_down(self) -> None:
        self.cursor = self._topic_cursor + 1

    # ------------------------------------------------------------------
    # Pane width
    # ------------------------------------------------------------------

    @property
    def left_width(self) -> int:
        return self._left_width

    @left_width.setter
    def left_width(self, value: int) -> None:
        self._left_width = max(10, min(value, 500))
        self._notify()

    def resize_left(self, delta: int = -5) -> None:
        self.left_width = self._left_width + delta

    def resize_right(self, delta: int = 5) -> None:
        self.left_width = self._left_width + delta

    def topic_at_cursor(self) -> str | None:
        topics = sorted(self._topics)
        if not topics:
            return None
        idx = self._topic_cursor - 1
        if idx < 0 or idx >= len(topics):
            return None
        return topics[idx]

    # ------------------------------------------------------------------
    # Message storage
    # ------------------------------------------------------------------

    def add_message(self, timestamp: str, topic: str, text: str) -> None:
        topic = self._normalize_topic(topic)
        self.add_topic(topic)
        self._monitor_messages.append((timestamp, topic, text))

    def get_filtered_messages(self) -> list[tuple[str, str, str]]:
        return [
            (ts, topic, text)
            for ts, topic, text in self._monitor_messages
            if self._topic_enabled.get(topic, True)
        ]

    def get_topics(self) -> list[str]:
        return sorted(self._topics)

    def is_enabled(self, topic: str) -> bool:
        return self._topic_enabled.get(topic, True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
