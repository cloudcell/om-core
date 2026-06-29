"""
CommandSession - Client-owned execution session.

Wraps SessionGateway for normalized command/query traffic.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING

from .executor import ExecutionContext, ExecutionResult

if TYPE_CHECKING:
    from .session_gateway import SessionGateway


class CommandSession:
    """
    A client-owned session handle.

    Usage:
        session = CommandSession(gateway, session_id)

    The public API (execute, query, context) is stable.
    """

    def __init__(self, gateway: "SessionGateway", session_id: str):
        self.gateway: "SessionGateway" = gateway
        self.session_id = session_id
        self._watch_all_hooks: dict[int, Callable[[str, Any], None]] = {}

    @property
    def context(self) -> Optional[ExecutionContext]:
        """Resolve context through SessionManager to avoid stale refs."""
        record = self.gateway.session_mgr.get_record(self.session_id)
        return record.context if record else None

    @context.setter
    def context(self, value: ExecutionContext) -> None:
        """Set context by updating the session record in the store."""
        record = self.gateway.session_mgr.get_record(self.session_id)
        if record is None:
            raise RuntimeError(f"Session '{self.session_id}' not found")
        record.context = value

    def require_context(self) -> ExecutionContext:
        """Return context or fail loudly if the session is invalid."""
        ctx = self.context
        if ctx is None:
            raise RuntimeError(f"Session '{self.session_id}' has no context")
        return ctx

    def execute(self, command_id: str, **params) -> ExecutionResult:
        """Execute a command through the gateway."""
        return self.gateway.send(self.session_id, command_id, **params)

    def query(self, query_type: str, **params) -> Any:
        """Convenience: execute a query and return the data directly."""
        return self.gateway.query(self.session_id, query_type, **params)

    def subscribe(self, topic: str, callback: Any) -> None:
        """Subscribe to a bus topic through the local MessageBus."""
        self.gateway.bus.subscribe(topic, callback)

    def unsubscribe(self, topic: str, callback: Any | None = None) -> None:
        """Unsubscribe from a bus topic."""
        if callback is None:
            # Bus unsubscribe requires a specific callback; no mass-unsubscribe.
            # Callers should hold their callback reference.
            return
        self.gateway.bus.unsubscribe(topic, callback)

    def watch_all(self, callback: Callable[[Any], None]) -> None:
        """Register a catch-all observer for every bus message.

        The callback receives the event envelope for every publish()
        call regardless of topic shape.
        """
        def _hook(topic: str, event: Any) -> None:
            callback(event)
        self._watch_all_hooks[id(callback)] = _hook
        self.gateway.bus.add_publish_hook(_hook)

    def unwatch_all(self, callback: Callable[[Any], None]) -> None:
        """Remove a catch-all observer added by watch_all()."""
        hook = self._watch_all_hooks.pop(id(callback), None)
        if hook is not None:
            self.gateway.bus.remove_publish_hook(hook)

    def get_variables(self) -> dict:
        """Return the session's local variables dict, or empty dict if unavailable."""
        ctx = self.context
        if ctx is None:
            return {}
        return getattr(ctx, "variables", {})

    def get_global_vars(self) -> dict:
        """Return the session's global variables dict, or empty dict if unavailable."""
        ctx = self.context
        if ctx is None:
            return {}
        return getattr(ctx, "global_vars", {})

    def get_workspace_snapshot(self) -> dict | None:
        """Return a workspace snapshot DTO, or None if unavailable."""
        return self.query("workspace_snapshot")
