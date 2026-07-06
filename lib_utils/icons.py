"""Icon storage retriever.

Icons are bundled in a single zip file (assets/icons/icons.zip) to avoid
thousands of loose SVG files in the working tree and in exports. This module
provides a non-Qt accessor that returns raw SVG bytes; GUI code can render them
with QSvgRenderer / QIcon.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import BinaryIO


ICON_ZIP = Path(__file__).resolve().parents[1] / "assets" / "icons" / "icons.zip"


class IconStore:
    """Read-only accessor for the zipped icon bundle.

    The zip layout mirrors the assets/icons/ tree:

        lucide/icons/<name>.svg
        tabler/icons/outline/<name>.svg
        tabler/icons/filled/<name>.svg

    Lookups are case-insensitive and accept the common "name.svg" suffix
    variations used by the icon sets.
    """

    def __init__(self, zip_path: Path | str = ICON_ZIP) -> None:
        self._zip_path = Path(zip_path)
        self._zip: zipfile.ZipFile | None = None
        self._index: dict[str, str] = {}

    def _open(self) -> zipfile.ZipFile:
        if self._zip is None:
            self._zip = zipfile.ZipFile(self._zip_path, "r")
            self._index = {name.lower(): name for name in self._zip.namelist()}
        return self._zip

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None
            self._index = {}

    def __enter__(self) -> IconStore:
        self._open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _resolve(self, name: str) -> str | None:
        key = name.lower().strip()
        if not key:
            return None
        # Accept both "file-plus.svg" and "lucide/file-plus.svg" style keys.
        return self._index.get(key)

    def get(self, name: str) -> bytes | None:
        """Return SVG bytes for the requested icon, or None if not found."""
        self._open()
        resolved = self._resolve(name)
        if resolved is None:
            return None
        return self._zip.read(resolved)

    def get_by_path(self, relative_path: str) -> bytes | None:
        """Return SVG bytes for a specific zip member path."""
        self._open()
        key = relative_path.strip().lower()
        if not key:
            return None
        resolved = self._index.get(key)
        if resolved is None:
            return None
        return self._zip.read(resolved)

    def exists(self, name: str) -> bool:
        """Check whether an icon exists in the bundle."""
        self._open()
        return self._resolve(name) is not None

    def list(self) -> list[str]:
        """Return all icon paths in the bundle."""
        return list(self._open().namelist())


# Module-level singleton for convenience.
_default_store: IconStore | None = None


def _get_default_store() -> IconStore:
    global _default_store
    if _default_store is None:
        _default_store = IconStore()
    return _default_store


def get_icon(name: str) -> bytes | None:
    """Return SVG bytes for the requested icon from the default store."""
    return _get_default_store().get(name)


def get_icon_by_path(relative_path: str) -> bytes | None:
    """Return SVG bytes for a specific zip member path from the default store."""
    return _get_default_store().get_by_path(relative_path)


def icon_exists(name: str) -> bool:
    """Check whether an icon exists in the default store."""
    return _get_default_store().exists(name)
