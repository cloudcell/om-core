"""Engine lifecycle state machine and serialized command guard.

This module owns the canonical engine states, the lock hierarchy, and the
single entry point used by all state-changing commands.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Any, Callable

from lib_contracts.types import CalculationCancelledError


class EngineState(Enum):
    """Canonical lifecycle states of the engine."""

    IDLE = "idle"
    MUTATING = "mutating"
    LOADING = "loading"
    RECALCULATING = "recalculating"
    CANCELLING = "cancelling"
    SAVING = "saving"
    FAULTED = "faulted"
    SHUTTING_DOWN = "shutting_down"


class EngineStateError(Exception):
    """Base class for command-layer engine state errors."""

    pass


class EngineBusyError(EngineStateError):
    """Raised when a command is rejected because the engine is busy."""

    pass


class EngineFaultedError(EngineStateError):
    """Raised when a non-recovery command is rejected because the engine is faulted."""

    pass


class EngineShuttingDownError(EngineStateError):
    """Raised when a command is rejected because the engine is shutting down."""

    pass


class _EngineStateMachine:
    """Internal state machine for a single engine instance.

    The authoritative state and lock fields live here. The engine core holds an
    instance and exposes it through the public `Engine` facade.
    """

    def __init__(self, event_publisher: Any | None = None, engine_facade: Any | None = None) -> None:
        self._event_publisher = event_publisher
        self._engine_facade = engine_facade
        self._state_lock = threading.RLock()
        self._mutation_lock = threading.Lock()
        self._engine_state = EngineState.IDLE
        self._cancel_requested = False
        self._active_command_id: str | None = None
        self._last_fault_reason: str | None = None
        self._watchdog_elapsed_ms = 0
        self._transition_counter = 0

    # --- read API ---------------------------------------------------------

    def get_engine_state(self) -> EngineState:
        with self._state_lock:
            return self._engine_state

    def get_diagnostics(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "current_state": self._engine_state.value,
                "last_fault_reason": self._last_fault_reason,
                "active_command_id": self._active_command_id,
                "watchdog_elapsed_ms": self._watchdog_elapsed_ms,
                "cancel_requested": self._cancel_requested,
            }

    # --- state transitions -------------------------------------------------

    def _enter_state(self, new_state: EngineState, reason: str | None = None) -> None:
        with self._state_lock:
            old_state = self._engine_state
            if old_state is new_state:
                return
            self._transition_counter += 1
            self._engine_state = new_state
            if new_state is not EngineState.CANCELLING:
                # CANCELLING is driven by the cancel command; do not clear the flag there.
                pass
            self._publish_state_change(old_state, new_state, reason)

    def _publish_state_change(
        self,
        old_state: EngineState,
        new_state: EngineState,
        reason: str | None,
    ) -> None:
        if self._event_publisher is None or self._engine_facade is None:
            return
        try:
            payload = {
                "old_state": old_state.value,
                "new_state": new_state.value,
                "timestamp": None,  # publisher may add its own timestamp
                "reason": reason,
            }
            self._event_publisher.publish("engine.state_changed", payload, self._engine_facade)
        except Exception:
            # Event publishing must never break the engine state machine.
            pass

    # --- cancellation ------------------------------------------------------

    def request_cancel(self) -> None:
        """Request cancellation of the active mutation/load/recalculation.

        Allowed only from ``MUTATING``, ``LOADING``, or ``RECALCULATING``.
        From ``IDLE`` it is a no-op; from ``SAVING`` it raises
        ``EngineBusyError``; from ``FAULTED`` it raises
        ``EngineFaultedError``; from ``SHUTTING_DOWN`` it raises
        ``EngineShuttingDownError``.
        """
        with self._state_lock:
            current = self._engine_state
            if current is EngineState.IDLE:
                return
            if current is EngineState.SAVING:
                raise EngineBusyError("Save is not cancellable")
            if current is EngineState.FAULTED:
                raise EngineFaultedError("Engine is faulted")
            if current is EngineState.SHUTTING_DOWN:
                raise EngineShuttingDownError("Engine is shutting down")
            if current not in (
                EngineState.MUTATING,
                EngineState.LOADING,
                EngineState.RECALCULATING,
            ):
                raise EngineBusyError(f"Cannot cancel while engine is {current.value}")
            self._cancel_requested = True
            self._enter_state(EngineState.CANCELLING, reason="cancel_requested")

    def is_cancel_requested(self) -> bool:
        with self._state_lock:
            return self._cancel_requested

    def reset_cancel(self) -> None:
        with self._state_lock:
            self._cancel_requested = False

    # --- serialized command entry point ------------------------------------

    def execute_serialized_command(
        self,
        command_id: str,
        allowed_states: set[EngineState],
        target_state: EngineState,
        body: Callable[[], Any],
        *,
        is_recovery: bool = False,
        next_state: EngineState | None = None,
        next_state_reason: str | None = None,
    ) -> Any:
        """Run a state-changing command body under the serialized-command lock.

        Args:
            command_id: Identifier for logging/diagnostics.
            allowed_states: States in which this command may start.
            target_state: State to enter once the mutation lock is acquired.
            body: Callable that performs the command work. It may query the
                state machine via ``engine.state_machine`` to transition to
                further states (e.g., ``MUTATING`` -> ``RECALCULATING``).
            is_recovery: Whether this command is a recovery command allowed from
                ``FAULTED``.
            next_state: Optional final state to enter after ``body()`` succeeds.
                If omitted, the body is responsible for calling
                ``transition_to`` itself.
            next_state_reason: Reason recorded for the optional ``next_state``
                transition.

        Raises:
            EngineBusyError: If the engine is busy and cannot accept the command.
            EngineFaultedError: If the engine is faulted and this is not a recovery command.
            EngineShuttingDownError: If the engine is shutting down.
        """
        if not self._mutation_lock.acquire(blocking=False):
            current = self.get_engine_state()
            if current is EngineState.FAULTED:
                raise EngineFaultedError(f"Engine is faulted; command {command_id} rejected")
            if current is EngineState.SHUTTING_DOWN:
                raise EngineShuttingDownError(f"Engine is shutting down; command {command_id} rejected")
            raise EngineBusyError(f"Engine is busy ({current.value}); command {command_id} rejected")

        try:
            with self._state_lock:
                current = self._engine_state
                if current not in allowed_states:
                    if current is EngineState.FAULTED:
                        if not is_recovery:
                            raise EngineFaultedError(
                                f"Engine is faulted; command {command_id} is not a recovery command"
                            )
                    elif current is EngineState.SHUTTING_DOWN:
                        raise EngineShuttingDownError(
                            f"Engine is shutting down; command {command_id} rejected"
                        )
                    else:
                        raise EngineBusyError(
                            f"Engine is in {current.value}; command {command_id} not allowed"
                        )
                self._active_command_id = command_id
                self._enter_state(target_state, reason=f"command_start:{command_id}")

            try:
                result = body()
                if next_state is not None:
                    self._enter_state(next_state, reason=next_state_reason)
                return result
            except CalculationCancelledError:
                self._enter_state(EngineState.CANCELLING, reason="cancel_requested")
                self._enter_state(EngineState.FAULTED, reason="user_cancelled")
                raise
            except Exception as exc:
                self._last_fault_reason = f"{type(exc).__name__}: {exc}"
                self._enter_state(EngineState.FAULTED, reason=f"exception:{type(exc).__name__}")
                raise
        finally:
            self._active_command_id = None
            self._mutation_lock.release()

    def transition_to(
        self,
        new_state: EngineState,
        *,
        reason: str | None = None,
    ) -> None:
        """Transition the engine to a new state while inside a serialized command.

        This helper is intended for command bodies that need to move through
        multiple states (e.g., ``MUTATING`` -> ``RECALCULATING`` -> ``IDLE``).
        """
        with self._state_lock:
            old_state = self._engine_state
            if old_state is new_state:
                return
            self._transition_counter += 1
            self._engine_state = new_state
        self._publish_state_change(old_state, new_state, reason)

    # --- shutdown ----------------------------------------------------------

    def shutdown(self) -> None:
        """Move the engine to ``SHUTTING_DOWN``. Terminal state."""
        with self._state_lock:
            if self._engine_state is EngineState.SHUTTING_DOWN:
                return
            old_state = self._engine_state
            self._engine_state = EngineState.SHUTTING_DOWN
        self._publish_state_change(old_state, EngineState.SHUTTING_DOWN, reason="shutdown")
