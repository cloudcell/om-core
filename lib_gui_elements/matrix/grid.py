"""Grid geometry and coordinate transformation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class GridGeometry:
    """Handles coordinate transformations and geometry calculations."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid
        self._leaf_index_cache: list[int] = []
        self._leaf_to_visual_cache: dict[int, int] = {}

    def _rebuild_leaf_index_cache(self) -> None:
        """Rebuild the display_row -> leaf_index mapping cache."""
        cache = []
        reverse_cache: dict[int, int] = {}
        leaf_count = 0
        for i, row in enumerate(self._grid._rows):
            if row.get("is_leaf", False):
                reverse_cache[leaf_count] = i
                leaf_count += 1
            cache.append(max(0, leaf_count - 1))
        self._leaf_index_cache = cache
        self._leaf_to_visual_cache = reverse_cache

    def leaf_row_index(self, display_row: int) -> int:
        """Map visible display row -> leaf index in _row_keys (group rows don't count)."""
        if not self._leaf_index_cache:
            self._rebuild_leaf_index_cache()
        if 0 <= display_row < len(self._leaf_index_cache):
            return self._leaf_index_cache[display_row]
        return max(0, len(self._leaf_index_cache) - 1)

    def visual_row_for_leaf(self, leaf_index: int) -> int | None:
        """Map leaf index -> display row (reverse of leaf_row_index)."""
        if not self._leaf_to_visual_cache:
            self._rebuild_leaf_index_cache()
        return self._leaf_to_visual_cache.get(leaf_index)

    def row_label_at(self, index: int) -> str:
        """Get display label for row at given index."""
        if 0 <= index < len(self._grid._rows):
            labels = self._grid._rows[index].get("labels") or []
            if labels:
                return str(labels[-1])
        return f"Row {index + 1}"

    def col_label_at(self, index: int) -> str:
        """Get display label for column at given index."""
        if 0 <= index < len(self._grid._cols):
            labels = self._grid._cols[index].get("labels") or []
            if labels:
                return str(labels[-1])
        return f"Col {index + 1}"

    def col_item_ids(self, col_idx: int) -> set[str]:
        """Return all item IDs for a column (for stacked dimensions)."""
        ids: set[str] = set()
        if 0 <= col_idx < len(self._grid._cols):
            col = self._grid._cols[col_idx]
            iid = col.get("item_id")
            if isinstance(iid, str):
                ids.add(iid)
            if 0 <= col_idx < len(self._grid._col_keys):
                ids.update(self._grid._col_keys[col_idx])
        return ids

    def row_item_ids(self, row_idx: int) -> set[str]:
        """Return all item IDs for a row (for stacked dimensions)."""
        ids: set[str] = set()
        if 0 <= row_idx < len(self._grid._rows):
            row = self._grid._rows[row_idx]
            iid = row.get("item_id")
            if isinstance(iid, str):
                ids.add(iid)
            if 0 <= row_idx < len(self._grid._row_keys):
                ids.update(self._grid._row_keys[row_idx])
        return ids

    def row_leaf_item_id(self, row_idx: int) -> str | None:
        """Return only the leaf item ID for a specific row."""
        if not (0 <= row_idx < len(self._grid._rows)):
            return None
        row = self._grid._rows[row_idx]
        if not row.get("is_leaf", False):
            return None
        iid = row.get("item_id")
        return iid if isinstance(iid, str) else None

    def col_leaf_item_id(self, col_idx: int) -> str | None:
        """Return only the leaf item ID for a specific column."""
        if not (0 <= col_idx < len(self._grid._cols)):
            return None
        col = self._grid._cols[col_idx]
        if not col.get("is_leaf", False):
            return None
        iid = col.get("item_id")
        return iid if isinstance(iid, str) else None

    def header_leaf_item_id(self, axis: str, index: int) -> str | None:
        """Return leaf item ID for header at given axis and index."""
        if axis == "row":
            return self.row_leaf_item_id(index)
        elif axis == "col":
            return self.col_leaf_item_id(index)
        return None

    def scroll_offset(self) -> "QtCore.QPoint":
        """Get current scroll offset."""
        from PySide6 import QtCore

        hbar = self._grid.horizontalScrollBar()
        vbar = self._grid.verticalScrollBar()
        return QtCore.QPoint(hbar.value(), vbar.value())

    def col_width(self, col_idx: int) -> int:
        """Get width for a specific column."""
        custom = self._grid._col_widths.get(col_idx)
        if custom is not None:
            return max(30, custom)
        return self._grid._m.col_w

    def row_header_width(self) -> int:
        """Calculate total row header width."""
        total = 0
        levels = getattr(self._grid, '_row_header_levels', 1)
        for level in range(levels):
            total += self.row_header_level_width(level)
        return total

    def row_header_level_width(self, level: int) -> int:
        """Get width for a specific row header level."""
        custom = self._grid._row_header_widths.get(level)
        if custom is not None:
            return max(20, custom)
        return self._grid._m.row_header_w
    def update_scrollbars(self) -> None:
        sz = self._content_size()
        vp = self.viewport().size()

        self.horizontalScrollBar().setPageStep(vp.width())
        self.verticalScrollBar().setPageStep(vp.height())

        self.horizontalScrollBar().setRange(0, max(0, sz.width() - vp.width()))
        self.verticalScrollBar().setRange(0, max(0, sz.height() - vp.height()))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scrollbars()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()


    def key_for_item_id(self, axis: str, item_id: str) -> tuple[str, ...] | None:
        """Return the key tuple containing the given item ID for the specified axis."""
        keys = self._col_keys if axis == "col" else self._row_keys
        entries = self._cols if axis == "col" else self._rows
        for idx, entry in enumerate(entries):
            iid = entry.get("item_id")
            if iid == item_id and 0 <= idx < len(keys):
                key = keys[idx]
                if isinstance(key, tuple):
                    return key
        return None


    def debug_print_layout(self) -> None:
        """Print grid layout to terminal for debugging."""
        print("\n" + "="*60)
        # Determine if axes are stacked (multi-dimension) or unstacked (single dimension)
        view = self._grid.current_view_meta()
        row_dim_ids = list(view.get("row_dim_ids", []) if view else [])
        col_dim_ids = list(view.get("col_dim_ids", []) if view else [])
        row_stacked = len(row_dim_ids) > 1
        col_stacked = len(col_dim_ids) > 1
        
        # Get max indices for unstacked logic
        max_row_idx = len(self._rows) - 1 if self._rows else 0
        max_col_idx = len(self._cols) - 1 if self._cols else 0
        
        print(f"GRID LAYOUT: {len(self._rows)} rows x {len(self._cols)} cols")
        print(f"ROW MODE: {'stacked' if row_stacked else 'unstacked'}")
        print(f"COL MODE: {'stacked' if col_stacked else 'unstacked'}")
        print("-"*60)
        
        if self._rows:
            print("ROWS:")
            for i, r in enumerate(self._rows):
                labels = r.get("labels", [])
                paths = r.get("label_paths", [])
                print(f"  {i}: labels={labels}, paths={paths}")
        
        if self._cols:
            print("\nCOLUMNS:")
            for i, c in enumerate(self._cols):
                labels = c.get("labels", [])
                paths = c.get("label_paths", [])
                print(f"  {i}: labels={labels}, paths={paths}")
        
        if self._col_bands:
            print("\nCOLUMN BANDS:")
            for b in self._col_bands:
                label = b.get("label", "")
                path = b.get("path")
                c0, c1 = b.get("c0", 0), b.get("c1", 0)
                path_str = str(path) if path else "None"
                c0, c1 = b.get("c0", 0), b.get("c1", 0)
                # Determine if this band would have shading
                # Unstacked: shade if label is not empty
                is_empty = not label and path is None
                is_group = False
                if not is_empty:
                    if col_stacked:
                        # Stacked: shade if path has more than one element
                        if isinstance(path, tuple) and len(path) > 1:
                            is_group = True
                    else:
                        # Unstacked: shade if label not empty
                        if label:
                            is_group = True
                shaded = "Y" if is_group else "N"
                print(f"  level={b.get('level')} c0={c0} c1={c1} label={label!r} path={path_str} shaded={shaded}")
        
        if self._row_bands:
            print("\nROW BANDS:")
            for b in self._row_bands:
                label = b.get("label", "")
                path = b.get("path")
                r0, r1 = b.get("r0", 0), b.get("r1", 0)
                path_str = str(path) if path else "None"
                r0, r1 = b.get("r0", 0), b.get("r1", 0)
                # Determine if this band would have shading
                # Unstacked: shade if label is not empty
                is_empty = not label and path is None
                is_group = False
                if not is_empty:
                    if row_stacked:
                        # Stacked: shade if path has more than one element
                        if isinstance(path, tuple) and len(path) > 1:
                            is_group = True
                    else:
                        # Unstacked: shade if label not empty
                        if label:
                            is_group = True
                shaded = "Y" if is_group else "N"
                print(f"  level={b.get('level')} r0={r0} r1={r1} label={label!r} path={path_str} shaded={shaded}")
        
        print("="*60 + "\n", flush=True)


    def resolve_row_leaf_target(self, row_idx: int) -> tuple[str, str, str] | None:
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        dim_ids = list(view.get("row_dim_ids", []) or []) if view else []
        if not dim_ids or not (0 <= row_idx < len(self._grid._rows)):
            return None
        if not self._grid._rows[row_idx].get("is_leaf", False):
            return None
        leaf_idx = self.leaf_row_index(row_idx)
        if not (0 <= leaf_idx < len(self._grid._row_keys)):
            return None
        row_key = self._grid._row_keys[leaf_idx]
        if not row_key or len(row_key) != len(dim_ids):
            return None
        dim_id = dim_ids[-1]
        item_id = row_key[-1]
        if not isinstance(item_id, str):
            return None
        dim = self._grid._workspace_read_model.get_dimension(dim_id)
        items = dim.get("items", []) if dim else []
        item = next((it for it in items if it["id"] == item_id), None)
        if item is None:
            return None
        return dim_id, item["id"], item["name"]

    def resolve_col_leaf_target(self, col_idx: int) -> tuple[str, str, str] | None:
        """Resolve column leaf target to (dim_id, item_id, item_name)."""
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        dim_ids = list(view.get("col_dim_ids", []) or []) if view else []
        if not dim_ids or not (0 <= col_idx < len(self._grid._cols)):
            return None
        if not self._grid._cols[col_idx].get("is_leaf", False):
            return None
        if not (0 <= col_idx < len(self._grid._col_keys)):
            return None
        col_key = self._grid._col_keys[col_idx]
        if not col_key or len(col_key) != len(dim_ids):
            return None
        dim_id = dim_ids[-1]
        item_id = col_key[-1]
        if not isinstance(item_id, str):
            return None
        dim = self._grid._workspace_read_model.get_dimension(dim_id)
        items = dim.get("items", []) if dim else []
        item = next((it for it in items if it["id"] == item_id), None)
        if item is None:
            return None
        return dim_id, item["id"], item["name"]

    def build_rows(self, view: Any, raw_row_keys: list[tuple[str, ...]]) -> None:
        """Build row structures from view and raw row keys."""
        self._grid._rows = []
        self._grid._row_keys = []
        row_dim_ids = list(getattr(view, "row_dim_ids", []) or [])

        if not row_dim_ids:
            # Single dimension case (original behavior)
            for r_i, key in enumerate(raw_row_keys):
                name = ""
                if key and isinstance(key[-1], str):
                    item_id = key[-1]
                    dim = self._grid._workspace_read_model.get_dimension(row_dim_ids[0]) if row_dim_ids else None
                    if dim:
                        items = dim.get("items", [])
                        item = next((it for it in items if it["id"] == item_id), None)
                        name = item["name"] if item else ""
                self._grid._rows.append(
                    {
                        "is_leaf": True,
                        "item_id": key[-1] if key else None,
                        "labels": [name],
                        "label_paths": [tuple()],
                        "path": (r_i,),
                    }
                )
            self._grid._row_keys = list(raw_row_keys)
            self._grid._row_header_levels = max(1, len(row_dim_ids))
            self._grid._row_band_levels = 0
            self._grid._row_bands = []
            return

        # Multiple row dimensions with grouping support
        outline_nodes = list(getattr(view, "row_outline", None) or [])
        if outline_nodes:
            self._grid._rows, self._grid._row_keys = self._build_rows_from_outline(
                raw_row_keys, outline_nodes, row_dim_ids
            )
        else:
            self._grid._rows, self._grid._row_keys = self._build_rows_flat(
                raw_row_keys, row_dim_ids
            )

        self._grid._row_header_levels = max(
            1,
            max((len(r.get("labels", [])) for r in self._grid._rows), default=len(row_dim_ids))
        )
        self._grid._row_band_levels = max(0, self._grid._row_header_levels - 1)
        self._grid._row_bands = self._grid._banding.compute_row_bands()

    def build_cols(self, view: Any, raw_col_keys: list[tuple[str, ...]]) -> None:
        """Build column structures from view and raw column keys."""
        self._grid._cols = []
        self._grid._col_keys = []
        col_dim_ids = list(getattr(view, "col_dim_ids", []) or [])

        if not col_dim_ids:
            # Single dimension case
            for c_i, key in enumerate(raw_col_keys):
                name = ""
                if key and isinstance(key[-1], str):
                    item_id = key[-1]
                    dim = self._grid._workspace_read_model.get_dimension(col_dim_ids[0]) if col_dim_ids else None
                    if dim:
                        items = dim.get("items", [])
                        item = next((it for it in items if it["id"] == item_id), None)
                        name = item["name"] if item else ""
                self._grid._cols.append(
                    {
                        "is_leaf": True,
                        "item_id": key[-1] if key else None,
                        "labels": [name],
                        "label_paths": [tuple()],
                        "path": (c_i,),
                    }
                )
            self._grid._col_keys = list(raw_col_keys)
            self._grid._col_header_levels = max(1, len(col_dim_ids))
            self._grid._col_band_levels = 0
            self._grid._col_bands = []
            return

        # Multiple column dimensions with grouping support
        outline_nodes = list(getattr(view, "col_outline", None) or [])
        if outline_nodes:
            self._grid._cols, self._grid._col_keys = self._build_cols_from_outline(
                raw_col_keys, outline_nodes, col_dim_ids
            )
        else:
            self._grid._cols, self._grid._col_keys = self._build_cols_flat(
                raw_col_keys, col_dim_ids
            )

        self._grid._col_header_levels = max(
            1,
            max((len(c.get("labels", [])) for c in self._grid._cols), default=len(col_dim_ids))
        )
        self._grid._col_band_levels = max(0, self._grid._col_header_levels - 1)
        self._grid._col_bands = self._grid._banding.compute_col_bands()

    def _build_rows_from_outline(
        self, raw_row_keys: list[tuple[str, ...]], outline_nodes: list[Any], row_dim_ids: list[str]
    ) -> tuple[list[dict], list[tuple[str, ...]]]:
        """Build rows from outline structure."""
        rows: list[dict] = []
        row_keys: list[tuple[str, ...]] = []
        key_map = {key: i for i, key in enumerate(raw_row_keys)}

        def _walk(nodes: list[Any], prefix_labels: list[str], prefix_paths: list, path_prefix: tuple, hidden: bool, depth: int) -> None:
            for idx, n in enumerate(nodes):
                item_id = getattr(n, "item_id", None)
                children = getattr(n, "children", None)
                is_group = item_id is None and isinstance(children, list) and bool(children)
                label = getattr(n, "label", None)
                path = path_prefix + (idx,)

                if is_group:
                    add_label = isinstance(label, str) and bool(label)
                    labels = prefix_labels + ([label] if add_label else [])
                    label_paths = prefix_paths + ([path] if add_label else [])

                    if children:
                        _walk(children, labels, label_paths, path, hidden or False, depth + 1)
                elif isinstance(item_id, str) and item_id in key_map:
                    if not hidden:
                        dim = self._grid._workspace_read_model.get_dimension(row_dim_ids[-1]) if row_dim_ids else None
                        name = ""
                        if dim:
                            items = dim.get("items", [])
                            item = next((it for it in items if it["id"] == item_id), None)
                            name = item["name"] if item else ""
                        final_labels = prefix_labels + [name]
                        final_label_paths = prefix_paths + [path]
                        rows.append(
                            {
                                "node_id": getattr(n, "node_id", None),
                                "item_id": item_id,
                                "labels": final_labels,
                                "label_paths": final_label_paths,
                                "path": path,
                                "display_edge_kind": getattr(n, "display_edge_kind", None),
                                "is_aggregate": getattr(n, "is_aggregate", False),
                                "is_leaf": True,
                            }
                        )
                        key_idx = key_map[item_id]
                        row_keys.append(raw_row_keys[key_idx])

        _walk(outline_nodes, [], [], tuple(), False, 1)
        return rows, row_keys

    def _build_rows_flat(
        self, raw_row_keys: list[tuple[str, ...]], row_dim_ids: list[str]
    ) -> tuple[list[dict], list[tuple[str, ...]]]:
        """Build rows in flat mode (no outline grouping)."""
        rows: list[dict] = []
        row_keys: list[tuple[str, ...]] = []

        dim_name_maps: list[dict[str, str]] = []
        dim_group_label_maps: list[dict[str, list[str]]] = []

        def _group_labels_by_item(nodes: list[Any]) -> dict[str, list[str]]:
            out: dict[str, list[str]] = {}
            def _walk(ns: list[Any], prefix: list[str]) -> None:
                for n in ns:
                    item_id = getattr(n, "item_id", None)
                    children = getattr(n, "children", None)
                    is_group = item_id is None and isinstance(children, list) and bool(children)
                    label = getattr(n, "label", None)
                    next_prefix = prefix
                    if is_group and isinstance(label, str) and label:
                        next_prefix = prefix + [label]
                    if is_group:
                        _walk(children, next_prefix)
                    elif isinstance(item_id, str):
                        out[item_id] = list(next_prefix)
            _walk(nodes, [])
            return out

        for did in row_dim_ids:
            dim = self._grid._workspace_read_model.get_dimension(did)
            items = dim.get("items", []) if dim else []
            dim_name_maps.append({it["id"]: it["name"] for it in items})
            outline_nodes = list(dim.get("outline", []) if dim else [])
            dim_group_label_maps.append(_group_labels_by_item(outline_nodes) if outline_nodes else {})

        dim_max_depths: list[int] = []
        for group_map in dim_group_label_maps:
            max_depth = 0
            for group_labels in group_map.values():
                max_depth = max(max_depth, len(group_labels))
            dim_max_depths.append(max_depth)

        for r_i, key in enumerate(raw_row_keys):
            labels: list[str] = []
            label_paths: list[tuple[int, ...] | None] = []

            for dim_idx, (iid, name_map, group_map) in enumerate(zip(key, dim_name_maps, dim_group_label_maps)):
                group_labels = list(group_map.get(iid, [])) if isinstance(iid, str) else []
                max_depth = dim_max_depths[dim_idx]

                for d in range(max_depth):
                    if d < len(group_labels):
                        labels.append(group_labels[d])
                        label_paths.append((dim_idx, d))
                    else:
                        labels.append("")
                        label_paths.append(None)

                if isinstance(iid, str):
                    labels.append(name_map.get(iid, ""))
                else:
                    labels.append("")
                label_paths.append((dim_idx,))

            rows.append(
                {
                    "is_leaf": True,
                    "item_id": key[-1] if key else None,
                    "labels": labels,
                    "label_paths": label_paths,
                    "path": (r_i,),
                }
            )
            row_keys.append(key)

        return rows, row_keys

    def _build_cols_from_outline(
        self, raw_col_keys: list[tuple[str, ...]], outline_nodes: list[Any], col_dim_ids: list[str]
    ) -> tuple[list[dict], list[tuple[str, ...]]]:
        """Build columns from outline structure."""
        cols: list[dict] = []
        col_keys: list[tuple[str, ...]] = []
        key_map = {key: i for i, key in enumerate(raw_col_keys)}

        def _walk(nodes: list[Any], prefix_labels: list[str], prefix_paths: list, path_prefix: tuple, hidden: bool, depth: int) -> None:
            for idx, n in enumerate(nodes):
                item_id = getattr(n, "item_id", None)
                children = getattr(n, "children", None)
                is_group = item_id is None and isinstance(children, list) and bool(children)
                label = getattr(n, "label", None)
                path = path_prefix + (idx,)

                if is_group:
                    add_label = isinstance(label, str) and bool(label)
                    labels = prefix_labels + ([label] if add_label else [])
                    label_paths = prefix_paths + ([path] if add_label else [])

                    if children:
                        _walk(children, labels, label_paths, path, hidden or False, depth + 1)
                elif isinstance(item_id, str) and item_id in key_map:
                    if not hidden:
                        dim = self._grid._workspace_read_model.get_dimension(col_dim_ids[-1]) if col_dim_ids else None
                        name = ""
                        if dim:
                            items = dim.get("items", [])
                            item = next((it for it in items if it["id"] == item_id), None)
                            name = item["name"] if item else ""
                        final_labels = prefix_labels + [name]
                        final_label_paths = prefix_paths + [path]
                        cols.append(
                            {
                                "node_id": getattr(n, "node_id", None),
                                "item_id": item_id,
                                "labels": final_labels,
                                "label_paths": final_label_paths,
                                "path": path,
                                "display_edge_kind": getattr(n, "display_edge_kind", None),
                                "is_aggregate": getattr(n, "is_aggregate", False),
                                "is_leaf": True,
                            }
                        )
                        key_idx = key_map[item_id]
                        col_keys.append(raw_col_keys[key_idx])

        _walk(outline_nodes, [], [], tuple(), False, 1)
        return cols, col_keys

    def _build_cols_flat(
        self, raw_col_keys: list[tuple[str, ...]], col_dim_ids: list[str]
    ) -> tuple[list[dict], list[tuple[str, ...]]]:
        """Build columns in flat mode (no outline grouping)."""
        cols: list[dict] = []
        col_keys: list[tuple[str, ...]] = []

        dim_name_maps: list[dict[str, str]] = []
        dim_group_label_maps: list[dict[str, list[str]]] = []

        def _group_labels_by_item(nodes: list[Any]) -> dict[str, list[str]]:
            out: dict[str, list[str]] = {}
            def _walk(ns: list[Any], prefix: list[str]) -> None:
                for n in ns:
                    item_id = getattr(n, "item_id", None)
                    children = getattr(n, "children", None)
                    is_group = item_id is None and isinstance(children, list) and bool(children)
                    label = getattr(n, "label", None)
                    next_prefix = prefix
                    if is_group and isinstance(label, str) and label:
                        next_prefix = prefix + [label]
                    if is_group:
                        _walk(children, next_prefix)
                    elif isinstance(item_id, str):
                        out[item_id] = list(next_prefix)
            _walk(nodes, [])
            return out

        for did in col_dim_ids:
            dim = self._grid._workspace_read_model.get_dimension(did)
            items = dim.get("items", []) if dim else []
            dim_name_maps.append({it["id"]: it["name"] for it in items})
            outline_nodes = list(dim.get("outline", []) if dim else [])
            dim_group_label_maps.append(_group_labels_by_item(outline_nodes) if outline_nodes else {})

        dim_max_depths: list[int] = []
        for group_map in dim_group_label_maps:
            max_depth = 0
            for group_labels in group_map.values():
                max_depth = max(max_depth, len(group_labels))
            dim_max_depths.append(max_depth)

        for c_i, key in enumerate(raw_col_keys):
            labels: list[str] = []
            label_paths: list[tuple[int, ...] | None] = []

            for dim_idx, (iid, name_map, group_map) in enumerate(zip(key, dim_name_maps, dim_group_label_maps)):
                group_labels = list(group_map.get(iid, [])) if isinstance(iid, str) else []
                max_depth = dim_max_depths[dim_idx]

                for d in range(max_depth):
                    if d < len(group_labels):
                        labels.append(group_labels[d])
                        label_paths.append((dim_idx, d))
                    else:
                        labels.append("")
                        label_paths.append(None)

                if isinstance(iid, str):
                    labels.append(name_map.get(iid, ""))
                else:
                    labels.append("")
                label_paths.append((dim_idx,))

            cols.append(
                {
                    "is_leaf": True,
                    "item_id": key[-1] if key else None,
                    "labels": labels,
                    "label_paths": label_paths,
                    "path": (c_i,),
                }
            )
            col_keys.append(key)

        return cols, col_keys
