"""Concrete EventPublisher that wraps engine events as MessageEnvelope and publishes to MessageBus."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from lib_openm.event_publisher import EventPublisher

from .message_bus import MessageEnvelope, get_message_bus
from .event_dto_projector import EventDTOProjector
from .executor import ExecutionContext


def _workspace_id_from_engine(engine: Any) -> str | None:
    """Safely extract workspace id from engine internals."""
    ws = getattr(engine, "workspace", None) or getattr(engine, "_ws", None)
    return getattr(ws, "id", None)


class BusEventPublisher(EventPublisher):
    """Publishes engine events to the MessageBus as MessageEnvelope."""

    def __init__(self, projector=None, bus=None):
        self.projector = projector or EventDTOProjector()
        self.bus = bus or get_message_bus()

    def publish(
        self,
        topic_suffix: str,
        payload: dict,
        engine: Any,
        correlation_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        try:
            enriched_payload = self.projector.enrich(topic_suffix, payload, engine)
            envelope = MessageEnvelope(
                message_id=str(uuid.uuid4()),
                message_type="event",
                topic=f"event.{topic_suffix}",
                correlation_id=correlation_id or str(uuid.uuid4()),
                session_id=session_id,
                client_type="engine",
                workspace_id=_workspace_id_from_engine(engine),
                actor_id=None,
                timestamp=time.perf_counter(),
                payload=enriched_payload,
                context=ExecutionContext(engine=engine),
                status="succeeded",
            )
            self.bus.publish(envelope.topic, envelope)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to publish engine event: event.%s", topic_suffix
            )
