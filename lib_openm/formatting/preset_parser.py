"""Preset parser: string -> FormatPreset dataclass."""

from __future__ import annotations

from typing import Mapping

from lib_contracts.types import (
    FormatArgValue,
    FormatKind,
    FormatPreset,
    InvalidFormatArgument,
    InvalidFormatString,
    UnknownFormatPreset,
    UnsupportedFormatPattern,
)


class PresetParser:
    """Parse ADR-0004 format strings into structured FormatPreset objects."""

    _VALID_KINDS: frozenset[str] = frozenset([
        "general",
        "number",
        "currency",
        "percent",
        "scientific",
        "boolean",
        "date",
        "time",
        "datetime",
    ])

    _REQUIRED_ARGS: dict[str, set[str]] = {
        "general": set(),
        "number": set(),
        "currency": {"code"},
        "percent": set(),
        "scientific": set(),
        "boolean": {"style"},
        "date": {"pattern"},
        "time": {"pattern"},
        "datetime": {"pattern"},
    }

    _DEFAULTS: dict[str, dict[str, FormatArgValue]] = {
        "general": {},
        "number": {"decimals": 2, "group": False, "negative": "minus", "zero": "normal"},
        "currency": {"decimals": 2, "symbol": False, "negative": "minus", "zero": "normal"},
        "percent": {"decimals": 0},
        "scientific": {"decimals": 2},
        "boolean": {},
        "date": {},
        "time": {},
        "datetime": {},
    }

    _VALID_BOOLEAN_STYLES: frozenset[str] = frozenset([
        "true_false",
        "yes_no",
        "one_zero",
    ])

    _VALID_NEGATIVE_STYLES: frozenset[str] = frozenset([
        "minus",
        "parentheses",
    ])

    _VALID_ZERO_STYLES: frozenset[str] = frozenset([
        "normal",
        "dash",
    ])

    @classmethod
    def parse(cls, text: str) -> FormatPreset:
        """Parse a normalized format string into a FormatPreset.

        Args:
            text: Normalized format string (outer quotes already stripped).

        Returns:
            A FormatPreset dataclass.

        Raises:
            InvalidFormatString: On malformed syntax.
            UnknownFormatPreset: On unknown preset kind.
            InvalidFormatArgument: On missing, invalid, or wrongly typed arguments.
            UnsupportedFormatPattern: On ``pattern:`` input (deferred for MVP).
        """
        text = text.strip()
        if not text:
            raise InvalidFormatString("Empty format string")
        if text == "general":
            return FormatPreset(kind="general", args={})
        if text.startswith("pattern:"):
            raise UnsupportedFormatPattern(
                f"pattern: is not supported in MVP: {text!r}"
            )
        if not text.startswith("preset:"):
            raise InvalidFormatString(
                f"Expected 'general', 'preset:...', or 'pattern:...', got: {text!r}"
            )

        body = text[len("preset:") :]
        paren_idx = body.find("(")
        if paren_idx == -1:
            raise InvalidFormatString(
                f"Preset missing argument list: {text!r}"
            )
        if not body.endswith(")"):
            raise InvalidFormatString(
                f"Preset argument list not closed: {text!r}"
            )

        kind = body[:paren_idx].strip()
        args_str = body[paren_idx + 1 : -1].strip()

        if kind not in cls._VALID_KINDS:
            raise UnknownFormatPreset(f"Unknown preset kind: {kind!r}")

        args = cls._parse_args(args_str, kind)
        # kind is guaranteed to be in _VALID_KINDS, so the cast is safe
        return FormatPreset(kind=kind, args=args)  # type: ignore[arg-type]

    @classmethod
    def _parse_args(cls, args_str: str, kind: str) -> dict[str, FormatArgValue]:
        result: dict[str, FormatArgValue] = {}
        if not args_str:
            defaults = cls._DEFAULTS.get(kind, {})
            return dict(defaults)

        segments = cls._split_args(args_str)
        for seg in segments:
            if "=" not in seg:
                raise InvalidFormatArgument(
                    f"Invalid argument syntax (missing '='): {seg!r}"
                )
            name, value_str = seg.split("=", 1)
            name = name.strip()
            value_str = value_str.strip()
            if not name:
                raise InvalidFormatArgument(
                    f"Empty argument name: {seg!r}"
                )
            value, was_quoted = cls._parse_value(value_str)
            result[name] = value
            cls._validate_arg(name, value, was_quoted, kind)

        defaults = cls._DEFAULTS.get(kind, {})
        for key, val in defaults.items():
            if key not in result:
                result[key] = val

        required = cls._REQUIRED_ARGS.get(kind, set())
        for req in required:
            if req not in result:
                raise InvalidFormatArgument(
                    f"Missing required argument for {kind!r}: {req!r}"
                )

        return result

    @classmethod
    def _split_args(cls, args_str: str) -> list[str]:
        segments: list[str] = []
        current = ""
        in_single = False
        in_double = False
        for ch in args_str:
            if ch == "'" and not in_double:
                in_single = not in_single
                current += ch
            elif ch == '"' and not in_single:
                in_double = not in_double
                current += ch
            elif ch == ";" and not in_single and not in_double:
                segments.append(current)
                current = ""
            else:
                current += ch
        if current:
            segments.append(current)
        return [s.strip() for s in segments if s.strip()]

    @classmethod
    def _parse_value(cls, s: str) -> tuple[FormatArgValue, bool]:
        """Parse a raw argument value and report whether it was quoted.

        Returns:
            A tuple of (parsed_value, was_quoted).
        """
        s = s.strip()
        was_quoted = False
        if len(s) >= 2:
            if s.startswith("'") and s.endswith("'"):
                return s[1:-1], True
            if s.startswith('"') and s.endswith('"'):
                return s[1:-1], True
        try:
            return int(s), False
        except ValueError:
            pass
        lower = s.lower()
        if lower == "true":
            return True, False
        if lower == "false":
            return False, False
        return s, False

    @classmethod
    def _validate_arg(
        cls,
        name: str,
        value: FormatArgValue,
        was_quoted: bool,
        kind: str,
    ) -> None:
        if name == "decimals":
            if not isinstance(value, int):
                raise InvalidFormatArgument(
                    f"Argument 'decimals' for {kind!r} must be an integer, got {value!r}"
                )
        elif name in ("group", "symbol"):
            if not isinstance(value, bool):
                raise InvalidFormatArgument(
                    f"Argument '{name}' for {kind!r} must be boolean (true/false), got {value!r}"
                )
        elif name == "style":
            if (
                not isinstance(value, str)
                or value not in cls._VALID_BOOLEAN_STYLES
            ):
                raise InvalidFormatArgument(
                    f"Argument 'style' must be one of {sorted(cls._VALID_BOOLEAN_STYLES)}, got {value!r}"
                )
        elif name == "code":
            if not isinstance(value, str) or not value:
                raise InvalidFormatArgument(
                    f"Argument 'code' must be a non-empty string, got {value!r}"
                )
        elif name == "pattern":
            if not was_quoted:
                raise InvalidFormatArgument(
                    f"Argument 'pattern' must be quoted, got {value!r}"
                )
            if not isinstance(value, str) or not value:
                raise InvalidFormatArgument(
                    f"Argument 'pattern' must be a non-empty quoted string, got {value!r}"
                )
        elif name == "negative":
            if not isinstance(value, str) or value not in cls._VALID_NEGATIVE_STYLES:
                raise InvalidFormatArgument(
                    f"Argument 'negative' must be one of {sorted(cls._VALID_NEGATIVE_STYLES)}, got {value!r}"
                )
        elif name == "zero":
            if not isinstance(value, str) or value not in cls._VALID_ZERO_STYLES:
                raise InvalidFormatArgument(
                    f"Argument 'zero' must be one of {sorted(cls._VALID_ZERO_STYLES)}, got {value!r}"
                )
