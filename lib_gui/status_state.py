"""Canonical status states for the GUI status bar.

This module is intentionally tiny: it defines the five user-facing states
and a priority map used by StatusManager to decide which active owner wins.
"""
from __future__ import annotations

from enum import Enum


class StatusState(str, Enum):
    WAITING_FOR_COMMAND = "waiting_for_command"
    LOADING = "loading"
    SAVING = "saving"
    CALCULATING = "calculating"
    ERROR = "error"


# Higher number = higher priority.  WAITING_FOR_COMMAND is not stored, so it
# does not appear here; it is the derived state when no owners are active.
PRIORITY = {
    StatusState.LOADING: 2,
    StatusState.SAVING: 2,
    StatusState.CALCULATING: 3,
    StatusState.ERROR: 4,
}
