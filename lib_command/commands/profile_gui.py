"""On-demand GUI profiling command."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from lib_command.core.message_bus import MessageBus, MessageEnvelope, get_message_bus
from lib_command.commands.profiler_register import (
    _registered_endpoints,
    _registry_lock,
    resolve_profiler_endpoint,
)
from lib_utils.config import gui


MAX_PROFILE_DURATION_SECONDS = gui("profiler", "max_duration_seconds", 300)
PROFILE_SHORT_HEADROOM_SECONDS = gui("profiler", "short_headroom_seconds", 15)
PROFILE_LONG_HEADROOM_SECONDS = gui("profiler", "long_headroom_seconds", 60)
PROFILE_LONG_THRESHOLD_SECONDS = gui("profiler", "long_profile_threshold_seconds", 10)


# Pending profile_gui requests: request_id -> {"event": threading.Event, "result": Any}
_pending_requests: dict[str, dict[str, Any]] = {}
_pending_requests_lock = threading.Lock()


def cmd_profile_gui(
    ctx: Any,
    endpoint_id: str,
    duration_seconds: float,
) -> dict:
    """Request a GUI profiling session and wait for the snapshot.

    Args:
        endpoint_id: Registered GUI endpoint ID (e.g. ``gui:<uuid>``) or a
            cardinal alias (``1``, ``2``, ...).
        duration_seconds: Profiling duration in seconds (max 10).

    Returns:
        Span snapshot dict on success, or ``{"error": "...", "request_id": ...}``
        on failure/timeout.
    """
    if duration_seconds <= 0:
        return {
            "error": f"duration_seconds must be positive, got {duration_seconds}",
            "request_id": None,
        }

    capped_duration = min(duration_seconds, MAX_PROFILE_DURATION_SECONDS)

    resolved = _resolve_and_wait_for_endpoint(endpoint_id)
    if resolved is None:
        return {
            "error": f"Unknown profiler endpoint: {endpoint_id}",
            "request_id": None,
        }

    request_id = uuid.uuid4().hex
    event = threading.Event()

    with _pending_requests_lock:
        _pending_requests[request_id] = {"event": event, "result": None}

    bus = _get_bus(ctx)
    logging.warning("[profiler] Publishing event.profiler.start for endpoint=%s duration=%.2fs request_id=%s", resolved, capped_duration, request_id)
    try:
        bus.publish(
            "event.profiler.start",
            MessageEnvelope(
                message_id=uuid.uuid4().hex,
                message_type="event",
                topic="event.profiler.start",
                correlation_id=request_id,
                session_id=None,
                client_type=None,
                workspace_id=None,
                actor_id=None,
                timestamp=time.perf_counter(),
                payload={
                    "endpoint_id": resolved,
                    "duration_seconds": capped_duration,
                    "request_id": request_id,
                },
                context=None,
            ),
        )

        # Add generous headroom: the GUI may be blocked by paint/recompute
        # (especially with the Julia engine) before it can start profiling and
        # report back, so total wait is not just duration.
        headroom = (
            PROFILE_LONG_HEADROOM_SECONDS
            if capped_duration >= PROFILE_LONG_THRESHOLD_SECONDS
            else PROFILE_SHORT_HEADROOM_SECONDS
        )
        timeout = capped_duration + headroom
        logging.warning("[profiler] Waiting %.2fs for report request_id=%s", timeout, request_id)
        if not event.wait(timeout=timeout):
            logging.warning("[profiler] Timed out waiting for report request_id=%s", request_id)
            return {
                "error": f"Timeout waiting for profiler report for {endpoint_id}",
                "request_id": request_id,
            }
        logging.warning("[profiler] Report received for request_id=%s", request_id)

        with _pending_requests_lock:
            result = _pending_requests.get(request_id, {}).get("result")
        if result is None:
            return {
                "error": "Profiler report received but contained no snapshot",
                "request_id": request_id,
            }
        return result
    finally:
        with _pending_requests_lock:
            _pending_requests.pop(request_id, None)


def _is_endpoint_registered(endpoint_id: str) -> bool:
    with _registry_lock:
        return endpoint_id in _registered_endpoints


def _resolve_and_wait_for_endpoint(identifier: str) -> str | None:
    """Resolve an endpoint ID or cardinal alias, with a short retry."""
    resolved = resolve_profiler_endpoint(identifier)
    if resolved is not None:
        return resolved
    # Short grace-period retry for startup races.
    time.sleep(0.5)
    return resolve_profiler_endpoint(identifier)


def _get_bus(ctx: Any) -> MessageBus:
    # Prefer the bus from the execution context if available, otherwise fall back.
    bus = getattr(ctx, "bus", None)
    if bus is not None:
        return bus
    return get_message_bus()


def clear_pending_profile_requests() -> None:
    """Clear all pending profile requests (useful for tests)."""
    with _pending_requests_lock:
        for entry in _pending_requests.values():
            entry["event"].set()
        _pending_requests.clear()
