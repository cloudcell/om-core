"""Helper for publishing domain events as MessageEnvelope.

Phase 2 of trace-hardening plan.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .message_bus import MessageBus, MessageEnvelope


def publish_domain_event(
    bus: MessageBus,
    topic: str,
    payload: object,
    correlation_id: str | None = None,
    session_id: str | None = None,
    causation_id: str | None = None,
) -> MessageEnvelope:
    """Publish a domain event as a MessageEnvelope.

    Args:
        bus: MessageBus instance.
        topic: Canonical event topic (e.g., ``event.dimension.created``).
        payload: Raw event payload (dict, dataclass, or any object).
        correlation_id: Optional trace correlation ID.
        session_id: Optional session ID.
        causation_id: Optional causation ID (e.g., triggering command message_id).

    Returns:
        The created MessageEnvelope.
    """
    envelope = MessageEnvelope(
        message_id=str(uuid.uuid4()),
        message_type="event",
        topic=topic,
        correlation_id=correlation_id or str(uuid.uuid4()),
        session_id=session_id,
        client_type=None,
        workspace_id=None,
        actor_id=None,
        timestamp=time.perf_counter(),
        payload=payload if payload is not None else {},
        context=None,
        causation_id=causation_id,
        status="succeeded",
    )
    bus.publish(topic, envelope)
    return envelope
