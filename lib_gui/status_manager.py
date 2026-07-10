"""Deterministic ownership registry for the GUI status bar.

The status bar is owned by exactly one active owner per lifecycle.  The
displayed state is the highest-priority active owner; when the registry is
empty, the derived state is WAITING_FOR_COMMAND.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from PySide6 import QtCore

from lib_gui.status_state import PRIORITY, StatusState

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


class StatusManager(QtCore.QObject):
    """Registry of active status owners.

    Use :meth:`begin`/:meth:`end` for explicit async lifecycles (signals,
    threads, command event pairs) and :meth:`hold` for synchronous operations.
    """

    changed = QtCore.Signal(StatusState)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._owners: dict[str, StatusState] = {}

    def begin(self, owner: str, state: StatusState) -> None:
        """Register a new owner.  Duplicate owners raise RuntimeError."""
        if owner in self._owners:
            raise RuntimeError(f"Duplicate status owner {owner!r}")
        self._owners[owner] = state
        self._emit_current()

    def update(self, owner: str, state: StatusState) -> None:
        """Update the state of an already-active owner."""
        if owner not in self._owners:
            raise RuntimeError(f"Cannot update missing owner {owner!r}")
        self._owners[owner] = state
        self._emit_current()

    def end(self, owner: str) -> None:
        """Remove an owner.  Missing owners raise KeyError."""
        del self._owners[owner]
        self._emit_current()

    def has(self, owner: str) -> bool:
        """Return True if the owner is currently active."""
        return owner in self._owners

    @contextmanager
    def hold(self, owner: str, state: StatusState) -> Generator[None, None, None]:
        """Synchronous context manager for a single owner lifecycle.

        If the owner has already been ended when the context exits, the
        KeyError is logged and re-raised so lifecycle bugs are visible.
        """
        self.begin(owner, state)
        try:
            yield
        finally:
            try:
                self.end(owner)
            except KeyError:
                logger.exception(
                    "Status owner %r was already ended or never began", owner
                )
                raise

    def current(self) -> StatusState:
        """Return the currently displayed state.

        If no owners are active, return WAITING_FOR_COMMAND.  Equal priorities
        resolve by Python's stable max: the first inserted owner with that
        priority wins, which is deterministic enough because the labels are
        user-facing and the owner keys are unique.
        """
        if not self._owners:
            return StatusState.WAITING_FOR_COMMAND
        return max(self._owners.values(), key=lambda s: PRIORITY[s])

    def _emit_current(self) -> None:
        self.changed.emit(self.current())
