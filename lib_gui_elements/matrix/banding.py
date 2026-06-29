"""Band calculation helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class BandingHelper:
    """Helper methods for computing column and row bands."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def _is_band_shaded(self, path: tuple | None, label: str, is_stacked: bool) -> bool:
        """Determine if a band should be shaded based on path, label, and mode."""
        is_empty = not label and path is None
        if is_empty:
            return False
        if is_stacked:
            # Stacked: shade if path has more than one element (i.e., it's a group)
            return isinstance(path, tuple) and len(path) > 1
        else:
            # Unstacked: shade if label is not empty
            return bool(label)

    def compute_col_bands(self) -> list[dict[str, Any]]:
        """Compute column bands, filling gaps with empty placeholders for alignment."""
        cols = self._grid._cols
        levels = self._grid._col_band_levels
        bands: list[dict[str, Any]] = []

        # Check if we're in stacked mode (multiple dimensions)
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        col_dim_ids = list(view.get("col_dim_ids", []) or [] if view else [])
        is_stacked = len(col_dim_ids) > 1

        for level in range(levels):
            cur_label: str | None = None
            cur_start = 0
            cur_path: tuple[int, ...] | None = None
            level_bands: list[dict[str, Any]] = []

            for i, c in enumerate(cols):
                labels = list(c.get("labels") or [])
                lab = labels[level] if level < max(0, len(labels) - 1) else ""
                paths = list(c.get("label_paths") or [])
                path = None
                if lab and 0 <= level < len(paths):
                    p = paths[level]
                    path = p if isinstance(p, tuple) else None

                if cur_label is None:
                    cur_label = lab
                    cur_start = i
                    cur_path = path
                elif lab != cur_label or path != cur_path:
                    level_bands.append({
                        "level": level,
                        "c0": cur_start,
                        "c1": i - 1,
                        "label": cur_label,
                        "path": cur_path,
                        "shaded": self._is_band_shaded(cur_path, cur_label, is_stacked),
                    })
                    cur_label = lab
                    cur_start = i
                    cur_path = path

            if cur_label is not None and cols:
                level_bands.append({
                    "level": level,
                    "c0": cur_start,
                    "c1": len(cols) - 1,
                    "label": cur_label,
                    "path": cur_path,
                    "shaded": self._is_band_shaded(cur_path, cur_label, is_stacked),
                })

            # Fill gaps with empty placeholders
            if level_bands and cols:
                filled_bands: list[dict[str, Any]] = []
                next_idx = 0
                for band in sorted(level_bands, key=lambda b: b["c0"]):
                    if band["c0"] > next_idx:
                        filled_bands.append({
                            "level": level, "c0": next_idx,
                            "c1": band["c0"] - 1, "label": "", "path": None,
                        })
                    filled_bands.append(band)
                    next_idx = band["c1"] + 1
                if next_idx < len(cols):
                    filled_bands.append({
                        "level": level, "c0": next_idx,
                        "c1": len(cols) - 1, "label": "", "path": None,
                    })
                bands.extend(filled_bands)
            elif cols:
                bands.append({
                    "level": level, "c0": 0, "c1": len(cols) - 1,
                    "label": "", "path": None,
                })

        return bands

    def band_path_for(self, paths: list, level: int) -> tuple | None:
        """Get the band path at a given level."""
        if 0 <= level < len(paths):
            p = paths[level]
            return p if isinstance(p, tuple) else None
        return None

    def compute_row_bands(self) -> list[dict[str, Any]]:
        """Compute row bands, filling gaps with empty placeholders for alignment."""
        rows = self._grid._rows
        levels = self._grid._row_band_levels
        bands: list[dict[str, Any]] = []

        # Check if we're in stacked mode (multiple dimensions)
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        row_dim_ids = list(view.get("row_dim_ids", []) or [] if view else [])
        is_stacked = len(row_dim_ids) > 1

        for level in range(levels):
            cur_label: str | None = None
            cur_start = 0
            cur_path: tuple[int, ...] | None = None
            level_bands: list[dict[str, Any]] = []

            for i, r in enumerate(rows):
                labels = list(r.get("labels") or [])
                lab = labels[level] if level < max(0, len(labels) - 1) else ""
                paths = list(r.get("label_paths") or [])
                path = None
                if lab and 0 <= level < len(paths):
                    p = paths[level]
                    path = p if isinstance(p, tuple) else None

                if cur_label is None:
                    cur_label = lab
                    cur_start = i
                    cur_path = path
                elif lab != cur_label or path != cur_path:
                    level_bands.append({
                        "level": level,
                        "r0": cur_start,
                        "r1": i - 1,
                        "label": cur_label,
                        "path": cur_path,
                        "shaded": self._is_band_shaded(cur_path, cur_label, is_stacked),
                    })
                    cur_label = lab
                    cur_start = i
                    cur_path = path

            if cur_label is not None and rows:
                level_bands.append({
                    "level": level,
                    "r0": cur_start,
                    "r1": len(rows) - 1,
                    "label": cur_label,
                    "path": cur_path,
                    "shaded": self._is_band_shaded(cur_path, cur_label, is_stacked),
                })

            # Fill gaps with empty placeholders
            if level_bands and rows:
                filled_bands: list[dict[str, Any]] = []
                next_idx = 0
                for band in sorted(level_bands, key=lambda b: b["r0"]):
                    if band["r0"] > next_idx:
                        filled_bands.append({
                            "level": level, "r0": next_idx,
                            "r1": band["r0"] - 1, "label": "", "path": None,
                        })
                    filled_bands.append(band)
                    next_idx = band["r1"] + 1
                if next_idx < len(rows):
                    filled_bands.append({
                        "level": level, "r0": next_idx,
                        "r1": len(rows) - 1, "label": "", "path": None,
                    })
                bands.extend(filled_bands)
            elif rows:
                bands.append({
                    "level": level, "r0": 0, "r1": len(rows) - 1,
                    "label": "", "path": None,
                })

        return bands

    def row_band_path_for(self, paths: list, level: int) -> tuple | None:
        """Get the row band path at a given level."""
        if 0 <= level < len(paths):
            p = paths[level]
            return p if isinstance(p, tuple) else None
        return None

    def col_band_path_for(self, level: int, col: dict[str, Any]) -> tuple[int, ...] | None:
        """Get the column band path at a given level from a column dict."""
        paths = list(col.get("label_paths") or [])
        if 0 <= level < len(paths):
            p = paths[level]
            return p if isinstance(p, tuple) else None
        return None

    def row_band_path_for_dict(self, level: int, row: dict[str, Any]) -> tuple[int, ...] | None:
        """Get the row band path at a given level from a row dict."""
        paths = list(row.get("label_paths") or [])
        if 0 <= level < len(paths):
            p = paths[level]
            return p if isinstance(p, tuple) else None
        return None
