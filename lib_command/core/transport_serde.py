"""JSON serialization for wire envelopes."""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

from .message_bus import MessageEnvelope


def _make_json_safe(value: Any) -> Any:
    """Recursively convert values to JSON-serializable form.

    Handles dataclasses via dataclasses.asdict, falls back to str() for
    anything else that json.dumps cannot handle.
    """
    if isinstance(value, dict):
        return {_make_json_safe(k): _make_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_make_json_safe(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _make_json_safe(dataclasses.asdict(value))
    return value


def envelope_to_wire(envelope: MessageEnvelope) -> dict:
    """Convert MessageEnvelope to JSON-serializable dict. Drops context."""
    return {
        "message_id": envelope.message_id,
        "message_type": envelope.message_type,
        "topic": envelope.topic,
        "correlation_id": envelope.correlation_id,
        "session_id": envelope.session_id,
        "client_type": envelope.client_type,
        "workspace_id": envelope.workspace_id,
        "actor_id": envelope.actor_id,
        "timestamp": envelope.timestamp,
        "payload": _make_json_safe(envelope.payload),
        "status": envelope.status,
        "command_id": envelope.command_id,
        "reply_to": envelope.reply_to,
        "causation_id": envelope.causation_id,
    }


def wire_to_envelope(data: dict, context: Any = None) -> MessageEnvelope:
    """Convert wire dict back to MessageEnvelope. Injects context server-side."""
    return MessageEnvelope(
        message_id=data.get("message_id", ""),
        message_type=data.get("message_type", ""),
        topic=data.get("topic", ""),
        correlation_id=data.get("correlation_id", ""),
        session_id=data.get("session_id"),
        client_type=data.get("client_type"),
        workspace_id=data.get("workspace_id"),
        actor_id=data.get("actor_id"),
        timestamp=data.get("timestamp", time.perf_counter()),
        payload=data.get("payload", {}),
        context=context,
        status=data.get("status", "accepted"),
        command_id=data.get("command_id", ""),
        reply_to=data.get("reply_to"),
        causation_id=data.get("causation_id"),
    )


def encode_envelope(envelope: MessageEnvelope) -> bytes:
    """Encode envelope to newline-delimited JSON bytes."""
    return json.dumps(envelope_to_wire(envelope), ensure_ascii=False, default=str).encode("utf-8") + b"\n"


def decode_envelope(data: bytes, context: Any = None) -> MessageEnvelope:
    """Decode newline-delimited JSON bytes to envelope."""
    try:
        wire = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to decode envelope: %s (data length=%d)", exc, len(data))
        try:
            dump_path = f"/tmp/om_decode_error_{int(time.time())}.json"
            with open(dump_path, "wb") as f:
                f.write(data)
            logger.error("Dumped raw envelope to %s", dump_path)
        except Exception:
            pass
        raise
    return wire_to_envelope(wire, context)
