"""Format renderer: FormatPreset + value -> display string."""

from __future__ import annotations

from lib_contracts.formatting import DeferredFormatRendering, InvalidFormatArgument, FormatPreset


class FormatRenderer:
    """Render cell values according to a parsed FormatPreset."""

    @classmethod
    def render(cls, value: object, preset: FormatPreset) -> str:
        """Render a value using the given FormatPreset.

        Args:
            value: The raw cell value (expected numeric for most presets).
            preset: Parsed format preset from PresetParser.

        Returns:
            Formatted display string.

        Raises:
            InvalidFormatArgument: If the value type is incompatible with the preset.
            DeferredFormatRendering: For date/time/datetime presets (deferred).
        """
        kind = preset.kind
        args = preset.args
        if kind == "general":
            return str(value)
        if kind == "number":
            return cls._render_number(value, args)
        if kind == "currency":
            return cls._render_currency(value, args)
        if kind == "percent":
            return cls._render_percent(value, args)
        if kind == "scientific":
            return cls._render_scientific(value, args)
        if kind == "boolean":
            return cls._render_boolean(value, args)
        if kind in ("date", "time", "datetime"):
            raise DeferredFormatRendering(
                f"Rendering for {kind!r} is deferred until serial-date convention exists"
            )
        raise InvalidFormatArgument(
            f"Unknown preset kind for rendering: {kind!r}"
        )

    @classmethod
    def _to_float(cls, value: object) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (ValueError, TypeError) as exc:
            raise InvalidFormatArgument(
                f"Format requires numeric input, got {value!r}"
            ) from exc

    @classmethod
    def _render_number(
        cls, value: object, args: Mapping[str, object]
    ) -> str:
        num = cls._to_float(value)
        decimals = args.get("decimals", 2)
        group = args.get("group", False)
        negative = str(args.get("negative", "minus"))
        zero = str(args.get("zero", "normal"))
        if not isinstance(decimals, int):
            decimals = 2
        amount = cls._format_amount(num, decimals, group, negative, zero)
        return amount

    @classmethod
    def _render_currency(
        cls, value: object, args: Mapping[str, object]
    ) -> str:
        num = cls._to_float(value)
        code = str(args.get("code", ""))
        decimals = args.get("decimals", 2)
        negative = str(args.get("negative", "minus"))
        zero = str(args.get("zero", "normal"))
        if not isinstance(decimals, int):
            decimals = 2
        # MVP: deterministic CODE amount rendering; grouping always on
        amount = cls._format_amount(num, decimals, True, negative, zero)
        return f"{code} {amount}"

    @classmethod
    def _format_amount(
        cls,
        num: float,
        decimals: int,
        group: bool,
        negative: str,
        zero: str,
    ) -> str:
        if num == 0.0 and zero == "dash":
            raw = "-"
            if negative == "parentheses":
                return f" {raw} "
            return raw
        group_spec = "," if group else ""
        raw = f"{abs(num):{group_spec}.{decimals}f}"
        if num < 0:
            if negative == "parentheses":
                return f"({raw})"
            return f"-{raw}"
        if negative == "parentheses":
            return f" {raw} "
        return raw

    @classmethod
    def _render_percent(
        cls, value: object, args: Mapping[str, object]
    ) -> str:
        num = cls._to_float(value)
        decimals = args.get("decimals", 0)
        if not isinstance(decimals, int):
            decimals = 0
        return f"{num * 100:.{decimals}f}%"

    @classmethod
    def _render_scientific(
        cls, value: object, args: Mapping[str, object]
    ) -> str:
        num = cls._to_float(value)
        decimals = args.get("decimals", 2)
        if not isinstance(decimals, int):
            decimals = 2
        return f"{num:.{decimals}E}"

    @classmethod
    def _render_boolean(
        cls, value: object, args: Mapping[str, object]
    ) -> str:
        style = str(args.get("style", "true_false"))
        is_true = cls._to_float(value) != 0.0
        if style == "true_false":
            return "TRUE" if is_true else "FALSE"
        if style == "yes_no":
            return "Yes" if is_true else "No"
        if style == "one_zero":
            return "1" if is_true else "0"
        raise InvalidFormatArgument(f"Unknown boolean style: {style!r}")
