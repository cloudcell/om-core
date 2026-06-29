"""Stable serialization helpers for persistence adapters.

These helpers keep deduplication and content-addressing logic independent of
engine serialization internals.
"""

from __future__ import annotations

import hashlib

from lib_storeadapters.json_file_adapter import workspace_to_json_string
from lib_storeadapters.ports import WorkspaceLike


def workspace_content_hash(workspace: WorkspaceLike) -> str:
    """Return a stable hash of the workspace's canonical serialized form.

    The serialization used here is deterministic (sorted JSON keys and stable
    whitespace) so that identical workspace state produces the same hash across
    calls.
    """
    json_str = workspace_to_json_string(workspace)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
