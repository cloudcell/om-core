"""Neutral utility for coercing user-entered values to canonical types."""

from typing import Any


def coerce_user_value(value: Any) -> Any:
    """Best-effort coercion for values coming from GUI edits."""

    if value is None:
        return None

    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        try:
            if "." in s:
                return float(s)
            return int(s)
        except Exception:
            return s

    return value
