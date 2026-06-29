"""Grid snapshot query helpers.

Viewport-cell key encoding, address resolution with explicit page selections,
CellFormat serialization, and channel allowlist.
"""

from __future__ import annotations

import json
from typing import Any

from lib_contracts.types import TECHNICAL_CHANNELS
from lib_openm.technical_ids import CHANNEL_TO_AT_ID

# Channel allowlist: full set of public channel names.
# All channels from lib_openm/technical_channels.py are accepted.
CHANNEL_ALLOWLIST: frozenset[str] = frozenset(TECHNICAL_CHANNELS)

CellFormatDict = dict[str, str | int | float | bool | None]


def validate_channels(channels: list[str]) -> None:
    """Validate requested channel names against the public allowlist.

    Raises ValueError with a clear message listing valid names if unknown
    channels are present.
    """
    unknown = [ch for ch in channels if ch not in CHANNEL_ALLOWLIST]
    if unknown:
        valid = ", ".join(sorted(CHANNEL_ALLOWLIST))
        raise ValueError(
            f"Unknown channel(s): {', '.join(unknown)}. "
            f"Valid channels: {valid}"
        )


# Re-export from lib_utils to keep command-layer stable while
# allowing GUI elements to import directly from the neutral layer.
from lib_utils.viewport_keys import make_viewport_cell_key, parse_viewport_cell_key


def resolve_addr(
    view,
    cube,
    row_key: tuple[str, ...],
    col_key: tuple[str, ...],
    page_selections: dict[str, str],
    channel: str | None = None,
) -> tuple[str, ...]:
    """Resolve a full cell address using explicit page selections.

    Replicates the logic of ``engine._addr_for_view_ids`` but uses the
    ``page_selections`` dict instead of hidden session/view state.

    Falls back to ``view.page_selections`` when the explicit dict is missing
    a dimension, so incomplete GUI payloads do not crash address resolution.
    """
    row_index = {did: i for i, did in enumerate(view.row_dim_ids)}
    col_index = {did: i for i, did in enumerate(view.col_dim_ids)}
    # Engine view state is the canonical fallback for missing GUI page selections.
    view_page_selections = getattr(view, "page_selections", {})

    def _page(dim_id: str) -> str | None:
        return page_selections.get(dim_id) or view_page_selections.get(dim_id)

    addr: list[str] = []
    for dim_id in cube.dimension_ids:
        if dim_id == "@" and channel:
            # When a channel is requested, always substitute the @ dimension
            # item with the channel-specific id, even if @ is stacked in
            # rows/columns.
            addr.append(CHANNEL_TO_AT_ID.get(channel, CHANNEL_TO_AT_ID["value"]))
        elif dim_id in row_index:
            i = row_index[dim_id]
            if 0 <= i < len(row_key):
                addr.append(row_key[i])
            else:
                page_item = _page(dim_id)
                if page_item is None:
                    raise ValueError(
                        f"Missing page selection for dimension '{dim_id}' "
                        f"(required for row key index {i})"
                    )
                addr.append(page_item)
        elif dim_id in col_index:
            i = col_index[dim_id]
            if 0 <= i < len(col_key):
                addr.append(col_key[i])
            else:
                page_item = _page(dim_id)
                if page_item is None:
                    raise ValueError(
                        f"Missing page selection for dimension '{dim_id}' "
                        f"(required for column key index {i})"
                    )
                addr.append(page_item)
        elif dim_id == "@":
            at_item = page_selections.get("@") or view_page_selections.get("@", CHANNEL_TO_AT_ID["value"])
            addr.append(at_item)
        else:
            page_item = _page(dim_id)
            if page_item is None:
                raise ValueError(
                    f"Missing page selection for dimension '{dim_id}'"
                )
            addr.append(page_item)
    return tuple(addr)


def cell_format_to_dict(fmt: Any) -> CellFormatDict:
    """Serialize a ``CellFormat`` dataclass instance to a plain dict.

    Uses the CellFormat attribute names as keys.  All values are primitives.
    """
    if fmt is None:
        return {}
    return {
        "bg_color": getattr(fmt, "bg_color", None),
        "font_color": getattr(fmt, "font_color", None),
        "font_family": getattr(fmt, "font_family", None),
        "font_size": getattr(fmt, "font_size", None),
        "font_weight": getattr(fmt, "font_weight", 400),
        "font_italic": getattr(fmt, "font_italic", False),
        "font": getattr(fmt, "font", None),
        "format_number": getattr(fmt, "format_number", "general"),
        "format_text": getattr(fmt, "format_text", ""),
        "format_null": getattr(fmt, "format_null", ""),
        "format_error": getattr(fmt, "format_error", ""),
        "number_format": getattr(fmt, "number_format", "general"),
        "decimal_places": getattr(fmt, "decimal_places", 2),
        "text_h_align": getattr(fmt, "text_h_align", "left"),
        "text_v_align": getattr(fmt, "text_v_align", "middle"),
        "text_indent": getattr(fmt, "text_indent", 0),
        "text_wrap": getattr(fmt, "text_wrap", False),
        "text_rotation": getattr(fmt, "text_rotation", 0),
        "border_top": getattr(fmt, "border_top", "none"),
        "border_bottom": getattr(fmt, "border_bottom", "none"),
        "border_left": getattr(fmt, "border_left", "none"),
        "border_right": getattr(fmt, "border_right", "none"),
        "border_diag_up": getattr(fmt, "border_diag_up", "none"),
        "border_diag_down": getattr(fmt, "border_diag_down", "none"),
        "border_style": getattr(fmt, "border_style", "solid"),
        "border_color": getattr(fmt, "border_color", "#000000"),
    }
