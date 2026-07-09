"""Minimal profiler endpoint registration.

Maintains an in-memory registry of registered GUI profiler endpoints. Each
endpoint is assigned a stable cardinal alias (1, 2, 3, ...) so it can be
referenced without typing its full UUID.
"""

from __future__ import annotations

import threading
from typing import Any


# Global endpoint registry.
_registered_endpoints: set[str] = set()
_endpoint_aliases: dict[str, int] = {}
_alias_to_endpoint: dict[int, str] = {}
_next_alias: int = 1
_registry_lock = threading.Lock()


def _assign_alias(endpoint_id: str) -> int:
    """Assign a new cardinal alias to an endpoint, or return its existing one."""
    global _next_alias
    if endpoint_id in _endpoint_aliases:
        return _endpoint_aliases[endpoint_id]
    alias = _next_alias
    _next_alias += 1
    _endpoint_aliases[endpoint_id] = alias
    _alias_to_endpoint[alias] = endpoint_id
    return alias


def cmd_profiler_register(ctx: Any, endpoint_id: str) -> dict:
    """Register a profiler endpoint ID and return its cardinal alias."""
    with _registry_lock:
        _registered_endpoints.add(endpoint_id)
        alias = _assign_alias(endpoint_id)
    return {"endpoint_id": endpoint_id, "alias": alias, "registered": True}


def cmd_profiler_unregister(ctx: Any, endpoint_id: str) -> dict:
    """Unregister a profiler endpoint ID and release its alias mapping."""
    with _registry_lock:
        _registered_endpoints.discard(endpoint_id)
        alias = _endpoint_aliases.pop(endpoint_id, None)
        if alias is not None:
            _alias_to_endpoint.pop(alias, None)
    return {"endpoint_id": endpoint_id, "unregistered": True}


def query_profiler_list(ctx: Any) -> list[dict[str, Any]]:
    """Return registered profiler endpoints with their cardinal aliases."""
    with _registry_lock:
        return [
            {"endpoint_id": ep, "alias": _endpoint_aliases[ep]}
            for ep in sorted(_registered_endpoints, key=lambda e: _endpoint_aliases[e])
        ]


def resolve_profiler_endpoint(identifier: str | int) -> str | None:
    """Resolve a cardinal alias or endpoint ID to a registered endpoint ID."""
    with _registry_lock:
        if isinstance(identifier, int):
            return _alias_to_endpoint.get(identifier)

        text = str(identifier).strip()
        if text in _registered_endpoints:
            return text

        if text.isdigit():
            return _alias_to_endpoint.get(int(text))

        return None


def clear_profiler_registry() -> None:
    """Clear all registered endpoints and aliases (useful for tests)."""
    global _next_alias
    with _registry_lock:
        _registered_endpoints.clear()
        _endpoint_aliases.clear()
        _alias_to_endpoint.clear()
        _next_alias = 1
