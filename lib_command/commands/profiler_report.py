"""Receive a profiler report from the GUI and signal the waiting command."""

from __future__ import annotations

import logging
from typing import Any

from lib_command.commands.profile_gui import (
    _pending_requests,
    _pending_requests_lock,
)


def cmd_profiler_report(ctx: Any, request_id: str, snapshot: dict) -> dict:
    """Receive a profiler report from the GUI and signal the waiting command.

    If ``request_id`` does not match a pending request, the call returns the
    snapshot gracefully without raising.
    """
    logging.warning("[profiler] Received report for request_id=%s", request_id)
    with _pending_requests_lock:
        entry = _pending_requests.get(request_id)
        if entry is None:
            logging.warning("[profiler] No pending request for request_id=%s", request_id)
            return snapshot
        entry["result"] = snapshot
        entry["event"].set()
        logging.warning("[profiler] Set result and signaled for request_id=%s", request_id)
    return snapshot
