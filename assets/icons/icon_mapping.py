"""Icon mappings for Qt integration.

Icons are stored in the zipped icon bundle at assets/icons/icons.zip.
CHANNEL_ICONS values are zip-relative paths (e.g. "lucide/icons/grid-3x3.svg")
so that callers can use either the zip store directly or the Qt helpers in
lib_gui.icons.
"""

from __future__ import annotations

LUCIDE_PREFIX = "lucide/icons"

CHANNEL_ICONS = {
    "@.value": f"{LUCIDE_PREFIX}/grid-3x3.svg",
    "@.fill": f"{LUCIDE_PREFIX}/palette.svg",
    "@.number_format": f"{LUCIDE_PREFIX}/hash.svg",
    "@.font_family": f"{LUCIDE_PREFIX}/type.svg",
    "@.font_size": f"{LUCIDE_PREFIX}/heading-1.svg",
    "@.font_color": f"{LUCIDE_PREFIX}/droplet.svg",
    "@.font_weight": f"{LUCIDE_PREFIX}/bold.svg",
    "@.font_italic": f"{LUCIDE_PREFIX}/italic.svg",
    "@.border": f"{LUCIDE_PREFIX}/square.svg",
    "@.border_top": f"{LUCIDE_PREFIX}/panel-top-open.svg",
    "@.border_bottom": f"{LUCIDE_PREFIX}/panel-bottom-open.svg",
    "@.border_left": f"{LUCIDE_PREFIX}/panel-left-open.svg",
    "@.border_right": f"{LUCIDE_PREFIX}/panel-right-open.svg",
    "@.alignment": f"{LUCIDE_PREFIX}/align-start-horizontal.svg",
    "@.text_h_align": f"{LUCIDE_PREFIX}/align-start-horizontal.svg",
    "@.text_v_align": f"{LUCIDE_PREFIX}/align-start-vertical.svg",
    "@.text_wrap": f"{LUCIDE_PREFIX}/text-wrap.svg",
    "@.text_indent": f"{LUCIDE_PREFIX}/space.svg",
    "@.text_rotation": f"{LUCIDE_PREFIX}/rotate-ccw.svg",
    "@.validation": f"{LUCIDE_PREFIX}/shield-check.svg",
    "@.protection": f"{LUCIDE_PREFIX}/lock.svg",
    "@.comment": f"{LUCIDE_PREFIX}/message-square.svg",
    "@.style": f"{LUCIDE_PREFIX}/palette.svg",
    "@.format_number": f"{LUCIDE_PREFIX}/hash.svg",
    "@.format_text": f"{LUCIDE_PREFIX}/type.svg",
    "all": f"{LUCIDE_PREFIX}/layers.svg",
    "filter": f"{LUCIDE_PREFIX}/funnel.svg",
    "clear": f"{LUCIDE_PREFIX}/x.svg",
    "search": f"{LUCIDE_PREFIX}/search.svg",
    "edit": f"{LUCIDE_PREFIX}/pencil.svg",
    "delete": f"{LUCIDE_PREFIX}/trash-2.svg",
    "add": f"{LUCIDE_PREFIX}/plus.svg",
    "expand": f"{LUCIDE_PREFIX}/chevron-down.svg",
    "collapse": f"{LUCIDE_PREFIX}/chevron-up.svg",
    "context": f"{LUCIDE_PREFIX}/target.svg",
    "viewport": f"{LUCIDE_PREFIX}/eye.svg",
    "empty": f"{LUCIDE_PREFIX}/circle-dashed.svg",
    "computing": f"{LUCIDE_PREFIX}/loader-circle.svg",
    "new": f"{LUCIDE_PREFIX}/sparkles.svg",
    "readonly": f"{LUCIDE_PREFIX}/lock.svg",
    "inherited": f"{LUCIDE_PREFIX}/git-branch.svg",
    "circle": f"{LUCIDE_PREFIX}/circle.svg",
    "check": f"{LUCIDE_PREFIX}/check.svg",
    "warning": f"{LUCIDE_PREFIX}/triangle-alert.svg",
    "info": f"{LUCIDE_PREFIX}/info.svg",
}


def get_icon_path(channel: str) -> str:
    """Get zip-relative path for a formula channel icon.

    The returned path can be passed to lib_utils.icons.get_icon_by_path or to
    lib_gui.icons.load_icon.
    """
    return CHANNEL_ICONS.get(channel, f"{LUCIDE_PREFIX}/circle.svg")


def get_icon_bytes(channel: str) -> bytes | None:
    """Get raw SVG bytes for a formula channel icon from the zipped bundle."""
    from lib_utils.icons import get_icon_by_path

    return get_icon_by_path(get_icon_path(channel))
