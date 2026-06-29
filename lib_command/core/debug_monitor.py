"""DebugMonitor — Bounded in-memory operational trace for the MessageBus.

Provides a lightweight, developer-facing view of recent bus activity.
Unlike Recorder, Monitor is runtime-oriented: no export, no durable storage,
just recent trace, errors, and correlation-chain lookup.

Monitor must not mutate messages, publish messages, or execute replay.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from lib_command.core.message_bus import MessageBus, MessageEnvelope

DEFAULT_MAX_ENTRIES = 1000


@dataclass(frozen=True)
class TraceEntry:
    """A lightweight view of a single bus message for debug inspection."""

    timestamp: float
    topic: str
    message_type: str
    correlation_id: str
    session_id: Optional[str]
    causation_id: Optional[str]
    status: str
    command_id: str
    payload_summary: str  # Short string for display; full payload kept separately


@dataclass
class DebugMonitor:
    """Bounded in-memory trace monitor for MessageBus activity.

    Usage::

        monitor = DebugMonitor(get_message_bus())
        # ... bus activity ...
        entries = monitor.recent(limit=50)
        errors = monitor.recent_errors(limit=10)
        chain = monitor.by_correlation("corr-abc")
    """

    bus: Optional[MessageBus] = None
    max_entries: int = DEFAULT_MAX_ENTRIES
    _entries: deque = field(default_factory=lambda: deque(maxlen=DEFAULT_MAX_ENTRIES), repr=False)
    _hook: Optional[Callable[[str, Any], None]] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Attach the publish hook if a bus is provided."""
        if self.bus is not None:
            self._attach_hook()
        # Ensure the deque respects the configured max even when
        # default_factory created it with a different maxlen.
        if self._entries.maxlen != self.max_entries:
            self._entries = deque(self._entries, maxlen=self.max_entries)

    # ------------------------------------------------------------------ #
    # Query API
    # ------------------------------------------------------------------ #

    def recent(self, limit: int = 100) -> list[TraceEntry]:
        """Return the most recent trace entries, newest last."""
        return list(self._entries)[-limit:]

    def by_correlation(self, correlation_id: str) -> list[TraceEntry]:
        """Return all entries sharing the given correlation_id."""
        return [e for e in self._entries if e.correlation_id == correlation_id]

    def by_session(self, session_id: str, limit: int = 100) -> list[TraceEntry]:
        """Return recent entries for a specific session_id."""
        matched = [e for e in self._entries if e.session_id == session_id]
        return matched[-limit:]

    def recent_errors(self, limit: int = 50) -> list[TraceEntry]:
        """Return recent entries whose status indicates failure."""
        errors = [e for e in self._entries if e.status in ("failed", "rejected", "error")]
        return errors[-limit:]

    def clear(self) -> None:
        """Remove all trace entries and detach from the bus."""
        self._entries.clear()
        self._detach_hook()

    # ------------------------------------------------------------------ #
    # Internal hook management
    # ------------------------------------------------------------------ #

    def _attach_hook(self) -> None:
        """Register the publish hook on the bus."""
        if self._hook is not None or self.bus is None:
            return
        self._hook = self._on_publish
        self.bus.add_publish_hook(self._hook)

    def _detach_hook(self) -> None:
        """Unregister the publish hook from the bus."""
        if self._hook is not None and self.bus is not None:
            self.bus.remove_publish_hook(self._hook)
        self._hook = None

    def _on_publish(self, topic: str, event: Any) -> None:
        """Hook called for every bus publish."""
        if isinstance(event, MessageEnvelope):
            self._add_envelope(topic, event)
        else:
            # Non-envelope events (legacy DTOs) are still traceable
            self._entries.append(
                TraceEntry(
                    timestamp=time.time(),
                    topic=topic,
                    message_type="unknown",
                    correlation_id="",
                    session_id=None,
                    causation_id=None,
                    status="unknown",
                    command_id="",
                    payload_summary=str(event)[:200],
                )
            )

    def _add_envelope(self, topic: str, envelope: MessageEnvelope) -> None:
        """Convert a MessageEnvelope into a TraceEntry and store it."""
        payload_str = str(envelope.payload)[:200]
        self._entries.append(
            TraceEntry(
                timestamp=envelope.timestamp or time.time(),
                topic=topic,
                message_type=envelope.message_type,
                correlation_id=envelope.correlation_id,
                session_id=envelope.session_id,
                causation_id=envelope.causation_id,
                status=envelope.status,
                command_id=envelope.command_id,
                payload_summary=payload_str,
            )
        )
