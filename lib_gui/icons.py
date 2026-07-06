"""Qt icon loaders backed by the zipped icon store.

This module bridges the non-Qt `lib_utils.icons` store with PySide6. It
provides helpers that return `QIcon`, `QPixmap`, and `QSvgRenderer` from the
zipped SVG bundle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter
from PySide6.QtSvg import QSvgRenderer

from lib_utils.icons import get_icon, get_icon_by_path

LUCIDE_PREFIX = "lucide/icons"

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStyle


def _svg_bytes(name: str) -> bytes:
    """Resolve icon name to SVG bytes.

    Supports several lookup styles:
    - "file-plus" or "file-plus.svg" -> searches both lucide and tabler outline sets
    - "lucide/file-plus.svg" -> specific set
    - "tabler/outline/file-plus.svg" -> specific style
    - "tabler/filled/file-plus.svg" -> specific style
    """
    # Normalise to a zip-relative file name.
    base = name.strip()
    if not base:
        raise FileNotFoundError(f"Icon name is empty")
    file_name = base if base.endswith(".svg") else f"{base}.svg"

    data = get_icon(base)
    if data is None:
        # Try the explicit zip member path (e.g. lucide/icons/paint-bucket.svg).
        data = get_icon_by_path(file_name)
    if data is None:
        # Try common prefixes for bare names. Most UI icons are tabler outline,
        # so prefer that set, then lucide, then tabler filled.
        for prefix in (
            f"tabler/icons/outline/{file_name}",
            f"lucide/icons/{file_name}",
            f"tabler/icons/filled/{file_name}",
        ):
            data = get_icon_by_path(prefix)
            if data is not None:
                break
    if data is None:
        raise FileNotFoundError(f"Icon not found in bundle: {name}")
    return data


def load_icon(name: str, size: int = 20, color: str = "#000000") -> QIcon:
    """Load a QIcon from the zipped icon bundle.

    Args:
        name: Icon name. Accepts "file-plus.svg", "lucide/file-plus.svg", or
              "tabler/outline/file-plus.svg".
        size: Target icon size in pixels.
        color: Fill color for SVG icons that use `currentColor`. Defaults to black.

    Returns:
        A QIcon. If the icon is not found, an empty QIcon is returned.
    """
    try:
        data = _svg_bytes(name)
    except FileNotFoundError:
        return QIcon()

    renderer = QSvgRenderer(QByteArray(data))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    colored = QPixmap(size, size)
    colored.fill(Qt.GlobalColor.transparent)
    painter = QPainter(colored)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), QColor(color))
    painter.end()

    return QIcon(colored)


def load_svg_renderer(name: str) -> QSvgRenderer:
    """Load a QSvgRenderer from the zipped icon bundle.

    Supports icon names and channel IDs (via `assets/icons/icon_mapping.py`).
    Unknown channel IDs fall back to the generic circle icon.
    Raises FileNotFoundError if the icon is missing.
    """
    # Try channel mapping first.
    from assets.icons.icon_mapping import CHANNEL_ICONS

    if name.startswith("@") or name in CHANNEL_ICONS:
        icon_path = CHANNEL_ICONS.get(name, f"{LUCIDE_PREFIX}/circle.svg")
        name = str(icon_path).replace("assets/icons/", "").replace("\\", "/")

    data = _svg_bytes(name)
    return QSvgRenderer(QByteArray(data))


def load_pixmap(name: str, size: int = 20) -> QPixmap:
    """Load a QPixmap from the zipped icon bundle.

    If the icon is not found, an empty pixmap is returned.
    """
    try:
        renderer = load_svg_renderer(name)
    except FileNotFoundError:
        return QPixmap()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def load_icon_colorized(name: str, size: int = 16, color: str = "#4B5563") -> QIcon:
    """Load a QIcon from the zipped icon bundle and colorize it.

    If the icon is not found, a solid-colored pixmap is returned.
    """
    try:
        renderer = load_svg_renderer(name)
    except FileNotFoundError:
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    colored = QPixmap(size, size)
    colored.fill(Qt.GlobalColor.transparent)
    painter = QPainter(colored)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), QColor(color))
    painter.end()

    return QIcon(colored)


def load_channel_icon(channel_id: str, size: int = 20) -> QIcon:
    """Load a QIcon for a formula channel using the channel mapping.

    Falls back to a generic circle icon if the channel is not mapped.
    """
    from assets.icons.icon_mapping import CHANNEL_ICONS

    icon_path = CHANNEL_ICONS.get(channel_id, "lucide/icons/circle.svg")
    # icon_path may be a Path from the old mapping; normalize to a string.
    name = str(icon_path)
    # If the old mapping returned a path like "assets/icons/lucide/icons/x.svg",
    # convert to the zip-relative style.
    name = name.replace("assets/icons/", "").replace("\\", "/")
    return load_icon(name, size=size)
