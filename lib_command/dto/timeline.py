"""Timeline DTOs for the command/query boundary.

These structures are plain data only. They must not import datastore
models, widget models, or adapter internals.
"""

from typing import TypedDict


class TimelineSnapshotDTO(TypedDict):
    """Neutral snapshot metadata returned by the timeline query.

    All fields are primitive JSON-serializable values. Ordering of a list
    of these DTOs is oldest-first by `created_at`, then `snapshot_id` as a
    deterministic tie-breaker.
    """

    snapshot_id: str
    parent_id: str | None
    description: str
    branch_name: str | None
    created_at: str  # ISO 8601 UTC
    snapshot_type: str
    is_delta: bool
