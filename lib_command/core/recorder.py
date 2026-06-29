"""Recorder — Dev/test message trace log for the MessageBus.

Observes all bus traffic via publish hooks, stores messages in-memory with
a bounded buffer, and supports NDJSON export for debugging and audit.

Recorder is dev/test-oriented only. It must not mutate engine state,
publish messages, or execute replay.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from lib_command.core.message_bus import MessageBus, MessageEnvelope
from lib_utils.jsonutil import to_jsonable

# Default maximum messages per recording to prevent unbounded growth.
DEFAULT_MAX_MESSAGES = 10000


@dataclass(frozen=True)
class RecordedMessage:
    """A single observed bus message."""

    topic: str
    envelope: MessageEnvelope


@dataclass(frozen=True)
class RecordingSummary:
    """Lightweight summary of a recording for listing."""

    recording_id: str
    session_id: Optional[str]
    started_at: float
    stopped_at: Optional[float]
    message_count: int


@dataclass
class Recording:
    """A complete in-memory recording of observed bus messages."""

    recording_id: str
    session_id: Optional[str]
    started_at: float
    stopped_at: Optional[float] = None
    messages: list[RecordedMessage] = field(default_factory=list)
    max_messages: int = DEFAULT_MAX_MESSAGES
    _dropped_count: int = field(default=0, repr=False)

    def add(self, topic: str, envelope: MessageEnvelope) -> None:
        """Append a message, dropping oldest if at capacity."""
        if len(self.messages) >= self.max_messages:
            self.messages.pop(0)
            self._dropped_count += 1
        self.messages.append(RecordedMessage(topic=topic, envelope=envelope))

    def summary(self) -> RecordingSummary:
        return RecordingSummary(
            recording_id=self.recording_id,
            session_id=self.session_id,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            message_count=len(self.messages),
        )


class Recorder:
    """Dev/test recorder that observes MessageBus traffic.

    Usage::

        recorder = Recorder(get_message_bus())
        rid = recorder.start_recording(session_id="sess-1")
        # ... commands run ...
        recording = recorder.stop_recording(rid)
        recorder.export_ndjson(rid, "/tmp/trace.ndjson")
    """

    def __init__(
        self,
        bus: Optional[MessageBus] = None,
        default_max_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        self.bus = bus
        self._default_max_messages = default_max_messages
        self._recordings: dict[str, Recording] = {}
        self._active: dict[str, Recording] = {}
        self._hook: Optional[Callable[[str, Any], None]] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start_recording(
        self,
        session_id: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> str:
        """Begin a new recording.

        Args:
            session_id: If given, only messages with this session_id are captured.
            max_messages: Per-recording buffer limit (defaults to class default).

        Returns:
            A unique recording id.
        """
        recording_id = f"rec-{uuid.uuid4().hex[:12]}"
        recording = Recording(
            recording_id=recording_id,
            session_id=session_id,
            started_at=time.time(),
            max_messages=max_messages or self._default_max_messages,
        )
        self._recordings[recording_id] = recording
        self._active[recording_id] = recording
        self._ensure_hook()
        return recording_id

    def stop_recording(self, recording_id: str) -> Recording:
        """Stop an active recording and return the full Recording.

        Raises:
            KeyError: If recording_id is unknown.
        """
        recording = self._recordings[recording_id]
        recording.stopped_at = time.time()
        self._active.pop(recording_id, None)
        self._maybe_remove_hook()
        return recording

    def list_recordings(self) -> list[RecordingSummary]:
        """Return summaries for all recordings (active and stopped)."""
        return [r.summary() for r in self._recordings.values()]

    def get_recording(self, recording_id: str) -> Recording:
        """Return the full Recording by id.

        Raises:
            KeyError: If recording_id is unknown.
        """
        return self._recordings[recording_id]

    def export_ndjson(self, recording_id: str, path: str) -> None:
        """Export a recording to newline-delimited JSON.

        The `context` field is omitted from NDJSON because it may contain
        non-serializable runtime objects (e.g., the engine).
        """
        recording = self._recordings[recording_id]
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for msg in recording.messages:
                line = _envelope_to_ndjson_line(msg.topic, msg.envelope)
                f.write(line)
                f.write("\n")

    def clear(self) -> None:
        """Remove all recordings and detach from the bus."""
        self._active.clear()
        self._recordings.clear()
        self._remove_hook()

    # ------------------------------------------------------------------ #
    # Internal hook management
    # ------------------------------------------------------------------ #

    def _ensure_hook(self) -> None:
        """Attach the publish hook if not already attached."""
        if self._hook is not None or self.bus is None:
            return
        self._hook = self._on_publish
        self.bus.add_publish_hook(self._hook)

    def _maybe_remove_hook(self) -> None:
        """Detach the publish hook if no recordings are active."""
        if not self._active:
            self._remove_hook()

    def _remove_hook(self) -> None:
        """Detach the publish hook unconditionally."""
        if self._hook is not None and self.bus is not None:
            self.bus.remove_publish_hook(self._hook)
        self._hook = None

    def _on_publish(self, topic: str, event: Any) -> None:
        """Hook called for every bus publish."""
        if not isinstance(event, MessageEnvelope):
            return
        for recording in list(self._active.values()):
            if recording.session_id is not None:
                if event.session_id != recording.session_id:
                    continue
            recording.add(topic, event)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #

def _envelope_to_ndjson_line(topic: str, envelope: MessageEnvelope) -> str:
    """Serialize a MessageEnvelope to a single NDJSON line.

    The `context` field is excluded because it may hold non-JSON-safe
    runtime objects (engine, views, etc.).
    """
    payload = {
        "message_id": envelope.message_id,
        "message_type": envelope.message_type,
        "topic": topic,
        "correlation_id": envelope.correlation_id,
        "session_id": envelope.session_id,
        "client_type": envelope.client_type,
        "workspace_id": envelope.workspace_id,
        "actor_id": envelope.actor_id,
        "causation_id": envelope.causation_id,
        "status": envelope.status,
        "command_id": envelope.command_id,
        "reply_to": envelope.reply_to,
        "timestamp": envelope.timestamp,
        "payload": envelope.payload,
    }
    safe = to_jsonable(payload)
    return json.dumps(safe, ensure_ascii=False, sort_keys=False)
