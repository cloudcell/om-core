"""Format string normalizer: strip outer quotes from format string literals."""

from __future__ import annotations

from .errors import InvalidFormatString


def normalize_format_string(raw: str) -> str:
    """Strip one outer matching quote pair from a raw format string literal.

    Preserves nested quotes. Rejects mismatched outer quotes.
    Does not evaluate escapes or execute anything.

    Args:
        raw: Raw format string, possibly wrapped in outer quotes.

    Returns:
        The unquoted format string.

    Raises:
        InvalidFormatString: If outer quotes are mismatched or malformed.
    """
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    stripped = raw.strip()
    if not stripped:
        return stripped
    first = stripped[0]
    last = stripped[-1]
    if first in ("'", '"'):
        if last != first:
            raise InvalidFormatString(
                f"Mismatched outer quotes in format string: {raw!r}"
            )
        if len(stripped) <= 2:
            raise InvalidFormatString(
                f"Empty quoted format string: {raw!r}"
            )
        return stripped[1:-1]
    return stripped
