"""Event publishing helper for RemoteEngine.

Maps integer event IDs from the server to Python message bus topics
and publishes events via the event publisher.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lib_openm.rpc_constants import _EVENT_ID_TO_TOPIC

if TYPE_CHECKING:
    from lib_openm.remote_engine import RemoteEngine

_log = logging.getLogger(__name__)


def publish_events(
    engine: "RemoteEngine",
    events: list[dict[str, Any]] | None,
) -> None:
    """Publish server events on the Python message bus.

    Each event is a dict with 'event_id' (int) and 'payload' (dict).
    The event_id is mapped to a Python topic string via _EVENT_ID_TO_TOPIC.
    """
    if not events:
        return

    publisher = engine._event_publisher
    if publisher is None or engine._suppress_events:
        return

    for evt in events:
        try:
            event_id = evt.get("event_id")
            topic = _EVENT_ID_TO_TOPIC.get(event_id)
            if topic is None:
                _log.warning("Unknown event_id %s from server", event_id)
                continue
            payload = evt.get("payload") or {}
            # BusEventPublisher.publish prepends "event." to the topic_suffix,
            # so strip it if present to avoid double-prefixing.
            if topic.startswith("event."):
                topic = topic[len("event."):]
            publisher.publish(topic, payload, engine)
        except Exception:
            _log.exception("Failed to publish remote event: %s", evt.get("event_id"))
