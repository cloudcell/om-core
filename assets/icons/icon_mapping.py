"""Icon mappings for Qt integration."""

from pathlib import Path

ICONS_DIR = Path(__file__).parent / "lucide" / "icons"

CHANNEL_ICONS = {
    "@.value": ICONS_DIR / "grid-3x3.svg",
    "@.fill": ICONS_DIR / "palette.svg",
    "@.number_format": ICONS_DIR / "hash.svg",
    "@.font_family": ICONS_DIR / "type.svg",
    "@.font_size": ICONS_DIR / "heading-1.svg",
    "@.font_color": ICONS_DIR / "droplet.svg",
    "@.font_weight": ICONS_DIR / "bold.svg",
    "@.font_italic": ICONS_DIR / "italic.svg",
    "@.border": ICONS_DIR / "square.svg",
    "@.border_top": ICONS_DIR / "panel-top-open.svg",
    "@.border_bottom": ICONS_DIR / "panel-bottom-open.svg",
    "@.border_left": ICONS_DIR / "panel-left-open.svg",
    "@.border_right": ICONS_DIR / "panel-right-open.svg",
    "@.alignment": ICONS_DIR / "align-start-horizontal.svg",
    "@.text_h_align": ICONS_DIR / "align-start-horizontal.svg",
    "@.text_v_align": ICONS_DIR / "align-start-vertical.svg",
    "@.text_wrap": ICONS_DIR / "text-wrap.svg",
    "@.text_indent": ICONS_DIR / "space.svg",
    "@.text_rotation": ICONS_DIR / "rotate-ccw.svg",
    "@.validation": ICONS_DIR / "shield-check.svg",
    "@.protection": ICONS_DIR / "lock.svg",
    "@.comment": ICONS_DIR / "message-square.svg",
    "@.style": ICONS_DIR / "palette.svg",
    "@.format_number": ICONS_DIR / "hash.svg",
    "@.format_text": ICONS_DIR / "type.svg",
    "all": ICONS_DIR / "layers.svg",
    "filter": ICONS_DIR / "funnel.svg",
    "clear": ICONS_DIR / "x.svg",
    "search": ICONS_DIR / "search.svg",
    "edit": ICONS_DIR / "pencil.svg",
    "delete": ICONS_DIR / "trash-2.svg",
    "add": ICONS_DIR / "plus.svg",
    "expand": ICONS_DIR / "chevron-down.svg",
    "collapse": ICONS_DIR / "chevron-up.svg",
    "context": ICONS_DIR / "target.svg",
    "viewport": ICONS_DIR / "eye.svg",
    "empty": ICONS_DIR / "circle-dashed.svg",
    "computing": ICONS_DIR / "loader-circle.svg",
    "new": ICONS_DIR / "sparkles.svg",
    "readonly": ICONS_DIR / "lock.svg",
    "inherited": ICONS_DIR / "git-branch.svg",
    "circle": ICONS_DIR / "circle.svg",
    "check": ICONS_DIR / "check.svg",
    "warning": ICONS_DIR / "triangle-alert.svg",
    "info": ICONS_DIR / "info.svg",
}

def get_icon_path(channel: str) -> Path:
    """Get SVG path for a formula channel."""
    return CHANNEL_ICONS.get(channel, ICONS_DIR / "circle.svg")
