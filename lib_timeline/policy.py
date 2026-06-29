"""lib_timeline.policy — snapshot cadence policy.

Pure policy module with no Engine/Workspace dependency.
Safe for import by GUI code.
"""

from __future__ import annotations


class SnapshotPolicy:
    """Policy for deciding when to create full vs delta snapshots."""

    def __init__(self, delta_threshold: int = 5):
        self.delta_threshold = delta_threshold
        self._delta_count = 0

    def should_create_full(self) -> bool:
        """Return True if the next snapshot should be a full snapshot."""
        return self._delta_count >= self.delta_threshold

    def record_delta(self) -> None:
        """Record that a delta snapshot was created."""
        self._delta_count += 1

    def record_full(self) -> None:
        """Record that a full snapshot was created."""
        self._delta_count = 0

    def reset(self) -> None:
        """Reset the delta counter."""
        self._delta_count = 0
