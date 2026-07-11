"""Status display subscriber for Event Bus.

This module provides a dedicated StatusDisplay class that subscribes to bus
events for REPL status display.

Phase A Step A.8: CLI/REPL bus-first migration
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class StatusDisplay:
    """Display command status via REPL prompt.

    Subscribes to session events and prints status messages to stderr
    so they do not corrupt readline / input() on stdout.

    Registered at REPL startup so event logging is available from day 1.
    Uses session.subscribe() so it works for both local and remote sessions.

    Bus topics subscribed:
    - command.*.succeeded: Display success status
    - command.*.failed: Display failure status
    """

    def __init__(
        self,
        session: Any = None,
        *,
        prompt: str = "",
        output_queue: Any | None = None,
        repl_state: Any | None = None,
    ) -> None:
        """Create StatusDisplay and register session subscribers.

        Args:
            session: A CommandSession or RemoteCommandSession. If None,
                     no subscriptions are registered (useful for tests).
            prompt:  Prompt string to reprint after async messages.
            output_queue: Thread-safe queue for deferring prints to the main thread.
            repl_state: ReplState instance to update for the status bar.
        """
        self._session = session
        self._prompt = prompt
        self._output_queue = output_queue
        self._repl_state = repl_state
        self._callbacks: list[tuple[str, Any]] = []
        self._session_id = getattr(session, "session_id", None) if session else None
        if session is not None:
            for topic in ("command.*.succeeded", "command.*.failed"):
                cb = (
                    self._on_command_succeeded
                    if "succeeded" in topic
                    else self._on_command_failed
                )
                session.subscribe(topic, cb)
                self._callbacks.append((topic, cb))

            cb_config = self._on_config_changed
            session.subscribe("event.system.config_changed", cb_config)
            self._callbacks.append(("event.system.config_changed", cb_config))

            # Seed initial MT state from engine so the status bar is accurate
            # even when the REPL starts after MT has already been toggled.
            try:
                if hasattr(session, "query"):
                    config = session.query("diagnostics_multithread_config") or {}
                    mt_enabled = bool(config.get("enabled", 0))
                    if repl_state is not None:
                        repl_state.mt_recompute = mt_enabled
            except Exception:
                pass

    def _print(self, text: str, *, event: Any | None = None) -> None:
        """Queue status message for postcmd flush."""
        if self._output_queue is not None:
            self._output_queue.put(text)
            return
        if sys.stderr.isatty():
            sys.stderr.write(f"\n{text}\n")
            sys.stderr.flush()
        else:
            print(text, file=sys.stderr)

    def _on_command_succeeded(self, event: Any) -> None:
        """Display success status when a command succeeds."""
        command_id = event.payload.get('command_id', 'unknown')
        event_session = getattr(event, "session_id", None)
        # Skip [OK] for our own commands; user already sees the result.
        if event_session == self._session_id:
            return
        self._print(f"[OK] {command_id}", event=event)

    def _on_config_changed(self, event: Any) -> None:
        """Update ReplState and queue a notice for postcmd flush."""
        payload = getattr(event, "payload", {}) or {}
        prop = payload.get("property")
        enabled = payload.get("enabled")
        if prop == "multithread_recompute" and enabled is not None:
            if self._repl_state is not None:
                self._repl_state.mt_recompute = bool(enabled)
            status = "enabled" if enabled else "disabled"
            self._print(f"[CONFIG] Multithreaded recompute {status}", event=event)
        elif prop == "incremental_recompute" and enabled is not None:
            status = "enabled" if enabled else "disabled"
            self._print(f"[CONFIG] Incremental recompute {status}", event=event)

    def close(self) -> None:
        """Unsubscribe all registered callbacks. Idempotent."""
        session = self._session
        if session is None:
            return
        for topic, cb in self._callbacks:
            try:
                if hasattr(session, "unsubscribe"):
                    session.unsubscribe(topic, cb)
            except Exception:
                pass
        self._callbacks.clear()
        self._session = None

    def _on_command_failed(self, event: Any) -> None:
        """Display failure status when a command fails."""
        command_id = event.payload.get('command_id', 'unknown')
        # Phase E: Suppress query failure noise — callers (CellReadModel,
        # GUIReadModelBinder) handle query failures gracefully. Only print
        # for commands where failure is exceptional.
        if command_id == "query":
            return
        error = event.payload.get('__error') or event.payload.get('error')
        if error:
            self._print(f"[FAIL] {command_id}: {error}", event=event)
        else:
            self._print(f"[FAIL] {command_id}", event=event)
