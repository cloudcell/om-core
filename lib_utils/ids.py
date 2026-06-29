from __future__ import annotations

import uuid


def new_id(prefix: str | None = None) -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value
