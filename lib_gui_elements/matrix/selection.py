"""Selection management for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6 import QtCore

from lib_contracts.types import OutlineNode

if TYPE_CHECKING:
    from PySide6 import QtGui, QtWidgets


class SelectionManager:
    """Manages selection state and operations for the grid."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid
        self._sel_row = 0
        self._sel_col = 0
        self._sel_mode: str = "cell"  # "cell", "row", "col"
        self._sel_indices: set[int] = set()  # For multi-selection of rows or cols
        # Anchor for range selections (Shift+arrow)
        self._anchor_row = 0
        self._anchor_col = 0
        # Flag to prevent selection reset during insert operations
        self._preserving_selection = False

    @property
    def sel_row(self) -> int:
        return self._grid._sel_row

    @sel_row.setter
    def sel_row(self, value: int) -> None:
        self._grid._sel_row = value

    @property
    def sel_col(self) -> int:
        return self._grid._sel_col

    @sel_col.setter
    def sel_col(self, value: int) -> None:
        self._grid._sel_col = value

    @property
    def sel_mode(self) -> str:
        return self._grid._sel_mode

    @sel_mode.setter
    def sel_mode(self, value: str) -> None:
        self._grid._sel_mode = value

    @property
    def sel_indices(self) -> set[int]:
        return self._grid._sel_indices

    @sel_indices.setter
    def sel_indices(self, value: set[int]) -> None:
        self._grid._sel_indices = value

    @property
    def anchor_row(self) -> int:
        return self._grid._anchor_row

    @anchor_row.setter
    def anchor_row(self, value: int) -> None:
        self._grid._anchor_row = value

    @property
    def anchor_col(self) -> int:
        return self._grid._anchor_col

    @anchor_col.setter
    def anchor_col(self, value: int) -> None:
        self._grid._anchor_col = value

    @property
    def preserving_selection(self) -> bool:
        return self._preserving_selection

    @preserving_selection.setter
    def preserving_selection(self, value: bool) -> None:
        self._preserving_selection = value

    def clamp_to_leaf(self) -> None:
        """Ensure selection is on a leaf cell, not on a group row."""
        grid = self._grid
        # Find the next leaf row at or after current position
        if 0 <= grid._sel_row < len(grid._rows):
            row = grid._rows[grid._sel_row]
            if not row.get("is_leaf", False):
                # Search forward for a leaf
                for i in range(grid._sel_row + 1, len(grid._rows)):
                    if grid._rows[i].get("is_leaf", False):
                        grid._sel_row = i
                        break
                else:
                    # No leaf found forward, search backward
                    for i in range(grid._sel_row - 1, -1, -1):
                        if grid._rows[i].get("is_leaf", False):
                            grid._sel_row = i
                            break

    def iter_selected_cells(self) -> list[tuple[int, int]]:
        """Return list of (r, c) tuples for all selected cells."""
        # Delegate to generator and convert to list for backward compatibility
        return list(self._iter_selected_cells_gen())

    def _iter_selected_cells_gen(self):
        """Generator that yields (r, c) tuples lazily - no massive list buildup."""
        grid = self._grid
        if grid._sel_mode == "cell":
            # Single cell or multi-cell selection
            seen = set()
            if grid._sel_indices:
                for item in grid._sel_indices:
                    if isinstance(item, tuple) and len(item) == 2:
                        r, c = item[0], item[1]
                        if (r, c) not in seen:
                            seen.add((r, c))
                            yield (r, c)
            if not seen:
                yield (grid._sel_row, grid._sel_col)
        elif grid._sel_mode == "row":
            for r in grid._sel_indices:
                if 0 <= r < len(grid._rows):
                    for c in range(len(grid._cols)):
                        yield (r, c)
        elif grid._sel_mode == "col":
            # LAZY: Yield cells for each selected column - one at a time
            for c in grid._sel_indices:
                if 0 <= c < len(grid._cols):
                    for r in range(len(grid._rows)):
                        yield (r, c)
        elif grid._sel_mode == "all":
            # All cells selected (corner click) - yield all cells
            for r in range(len(grid._rows)):
                for c in range(len(grid._cols)):
                    yield (r, c)

    def is_related_col(self, col_idx: int) -> bool:
        """Check if column is related to current selection (same dimension item)."""
        grid = self._grid
        if grid._sel_mode != "cell":
            return False
        if not (0 <= col_idx < len(grid._col_keys)):
            return False
        # Get active column's item IDs
        active_ids = self._active_col_item_ids()
        if not active_ids:
            return False
        # Check overlap
        col_ids = grid._col_item_ids(col_idx)
        return bool(active_ids & col_ids)

    def is_related_row(self, row_idx: int) -> bool:
        """Check if row is related to current selection (same dimension item)."""
        grid = self._grid
        if grid._sel_mode != "cell":
            return False
        if not (0 <= row_idx < len(grid._row_keys)):
            return False
        # Get active row's item IDs
        active_ids = self._active_row_item_ids()
        if not active_ids:
            return False
        # Check overlap
        row_ids = grid._row_item_ids(row_idx)
        return bool(active_ids & row_ids)

    def _active_col_item_ids(self) -> set[str]:
        """Return all item IDs for the currently selected column."""
        grid = self._grid
        ids: set[str] = set()
        if 0 <= grid._sel_col < len(grid._cols):
            col = grid._cols[grid._sel_col]
            iid = col.get("item_id")
            if isinstance(iid, str):
                ids.add(iid)
            if 0 <= grid._sel_col < len(grid._col_keys):
                ids.update(grid._col_keys[grid._sel_col])
        return ids

    def _active_row_item_ids(self) -> set[str]:
        """Return all item IDs for the currently selected row."""
        grid = self._grid
        ids: set[str] = set()
        if 0 <= grid._sel_row < len(grid._rows):
            row = grid._rows[grid._sel_row]
            iid = row.get("item_id")
            if isinstance(iid, str):
                ids.add(iid)
            if 0 <= grid._sel_row < len(grid._row_keys):
                ids.update(grid._row_keys[grid._sel_row])
        return ids

    def _active_row_leaf_item_id(self) -> str | None:
        """Return only the leaf item ID for the currently selected row."""
        grid = self._grid
        if not (0 <= grid._sel_row < len(grid._rows)):
            return None
        row = grid._rows[grid._sel_row]
        if not row.get("is_leaf", False):
            return None
        iid = row.get("item_id")
        return iid if isinstance(iid, str) else None

    def _active_col_leaf_item_id(self) -> str | None:
        """Return only the leaf item ID for the currently selected column."""
        grid = self._grid
        if not (0 <= grid._sel_col < len(grid._cols)):
            return None
        col = grid._cols[grid._sel_col]
        if not col.get("is_leaf", False):
            return None
        iid = col.get("item_id")
        return iid if isinstance(iid, str) else None

    def get_selected_rc(self) -> tuple[int, int]:
        """Return current selection as (row, col) tuple."""
        return (self._grid._sel_row, self._grid._sel_col)

    def get_selected_keys(self) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        """Return current selection as (row_key, col_key) tuple."""
        grid = self._grid
        if 0 <= grid._sel_row < len(grid._row_keys) and 0 <= grid._sel_col < len(grid._col_keys):
            return (grid._row_keys[grid._sel_row], grid._col_keys[grid._sel_col])
        return None

    def get_selected_cell_coords(self) -> list[tuple[int, int]]:
        """Return all selected cell coordinates."""
        return self.iter_selected_cells()

    def get_selected_cell_keys_many(self) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
        """Return selected cells as list of (row_key, col_key) tuples."""
        grid = self._grid
        result: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for r, c in self.iter_selected_cells():
            if 0 <= r < len(grid._row_keys) and 0 <= c < len(grid._col_keys):
                result.append((grid._row_keys[r], grid._col_keys[c]))
        return result
    def insert_dimension_items_relative_to_selection(self, axis: str, *, insert_after: bool) -> None:
        print(f"DEBUG insert_dimension_items: START axis={axis}, insert_after={insert_after}")
        grid = self._grid
        # Capture current selection before modification
        saved_sel_mode = grid._sel_mode
        saved_sel_indices = set(grid._sel_indices) if grid._sel_indices else set()
        saved_sel_row = grid._sel_row
        saved_sel_col = grid._sel_col
        print(f"DEBUG insert_dimension_items: saved_sel_mode={saved_sel_mode}, saved_sel_indices={saved_sel_indices}")
        
        indices = self.selected_contiguous_leaf_indices(axis)
        print(f"DEBUG insert_dimension_items: indices={indices}")
        if not indices:
            print(f"DEBUG insert_dimension_items: Returning early - no indices")
            return
        dim_id = self._grid._axis_dim_id(axis)
        print(f"DEBUG insert_dimension_items: dim_id={dim_id}")
        if not isinstance(dim_id, str):
            print(f"DEBUG insert_dimension_items: Returning early - dim_id not str")
            return

        entries = self._grid._rows if axis == "row" else self._grid._cols
        anchor_index = indices[-1] if insert_after else indices[0]
        anchor_entry = entries[anchor_index]
        anchor_item_id = anchor_entry.get("item_id")
        anchor_path = anchor_entry.get("path")
        print(f"DEBUG insert_dimension_items: anchor_item_id={anchor_item_id}, anchor_path={anchor_path}")
        if not isinstance(anchor_item_id, str):
            print(f"DEBUG insert_dimension_items: Returning early - anchor_item_id not str")
            return

        created_ids: list[str] = []
        for _ in indices:
            result = self._grid.execute_command(
                "create_dimension_item",
                dim_id=dim_id,
                name=self._grid._random_unique_dimension_item_name(dim_id),
                position="append",
            )
            if result.success and result.data:
                item_id = result.data.get("id") if isinstance(result.data, dict) else getattr(result.data, "id", None)
                if item_id:
                    created_ids.append(item_id)

        dim = self._grid._workspace_read_model.get_dimension(dim_id)
        if not dim:
            return
        items = dim.get("items", [])
        created_items = [it for it in items if it["id"] in created_ids]
        remaining_items = [it for it in items if it["id"] not in created_ids]
        anchor_pos = next((i for i, it in enumerate(remaining_items) if it["id"] == anchor_item_id), None)
        if anchor_pos is None:
            return
        insert_pos = anchor_pos + (1 if insert_after else 0)
        for i, item in enumerate(created_items):
            remaining_items.insert(insert_pos + i, item)

        # Route reordering through command spine
        new_order_ids = [it["id"] for it in remaining_items if it.get("id")]
        self._grid.execute_command(
            "set_dimension_item_order",
            dim_id=dim_id,
            item_ids=new_order_ids,
        )

        # Graph-first: check if outline is synced to graph
        has_system_cubes = self._grid._workspace_read_model.has_system_graph_cubes()
        outline = self._grid._axis_outline(axis)
        root = self._grid._outline_root(axis)

        def _all_synced(nodes):
            for n in nodes:
                if not getattr(n, 'node_id', None):
                    return False
                if n.children and not _all_synced(n.children):
                    return False
            return True

        outline_synced = has_system_cubes and root and _all_synced(root)
        anchor_synced = (
            outline_synced
            and isinstance(anchor_path, tuple)
            and anchor_path
            and self._grid._get_node_at_path(root, anchor_path) is not None
            and getattr(self._grid._get_node_at_path(root, anchor_path), 'node_id', None)
        )

        if anchor_synced:
            # Phase 7: Engine API resolves item_ids → node_ids and places them
            anchor_node = self._grid._get_node_at_path(root, anchor_path)
            anchor_in_group = len(anchor_path) > 1
            is_aggregate = getattr(anchor_node, 'is_aggregate', False)

            # When inserting after an aggregate, place outside the group so the
            # new item appears after the aggregate rather than before it.
            is_first_in_group = anchor_in_group and anchor_path[-1] == 0
            if insert_after and is_aggregate and anchor_in_group:
                parent_path = tuple(anchor_path[:-1])
                parent_node = self._grid._get_node_at_path(root, parent_path)
                grandparent_path = tuple(anchor_path[:-2]) if len(anchor_path) > 2 else ()
                grandparent_node = (
                    self._grid._get_node_at_path(root, grandparent_path)
                    if grandparent_path else None
                )
                parent_node_id = getattr(grandparent_node, 'node_id', None)
                anchor_node_id = getattr(parent_node, 'node_id', None)
                position = "after"
            elif not insert_after and is_first_in_group:
                # Insert before the first item in a group -> place outside the group
                parent_path = tuple(anchor_path[:-1])
                parent_node = self._grid._get_node_at_path(root, parent_path)
                grandparent_path = tuple(anchor_path[:-2]) if len(anchor_path) > 2 else ()
                grandparent_node = (
                    self._grid._get_node_at_path(root, grandparent_path)
                    if grandparent_path else None
                )
                parent_node_id = getattr(grandparent_node, 'node_id', None)
                anchor_node_id = getattr(parent_node, 'node_id', None)
                position = "before"
            else:
                parent_path = tuple(anchor_path[:-1]) if anchor_in_group else ()
                parent_node = self._grid._get_node_at_path(root, parent_path) if anchor_in_group else None
                parent_node_id = getattr(parent_node, 'node_id', None) if parent_node else None
                anchor_node_id = getattr(anchor_node, 'node_id', None)
                position = "after" if insert_after else "before"

            self._grid.execute_command(
                "place_item_nodes",
                dim_id=dim_id,
                item_ids=[item["id"] for item in created_items],
                parent_node_id=parent_node_id,
                anchor_node_id=anchor_node_id,
                position=position,
            )
        else:
            pass  # Phase 4: graph is canonical, outline must be synced

        # Set flag to prevent reload() from resetting selection
        grid._preserving_selection = True

        # Mark workspace as dirty after inserting dimension items
        print(f"[DEBUG] content_changed.emit() from selection.py insert_dimension_items")
        grid.content_changed.emit()
        
        # Defer selection restoration until after reload completes
        def _restore():
            try:
                print(f"DEBUG _restore: START saved_sel_mode={saved_sel_mode}, axis={axis}, saved_sel_indices={saved_sel_indices}, insert_after={insert_after}", flush=True)
                # Restore selection after reload, adjusting indices for inserted items
                grid._sel_mode = saved_sel_mode
                grid._sel_indices = saved_sel_indices
                
                # Adjust indices based on insertion
                if saved_sel_mode == axis:
                    # Selection is on the same axis that was modified
                    offset = len(indices) if not insert_after else 0
                    print(f"DEBUG _restore: Adjusting indices, offset={offset}, len(indices)={len(indices)}", flush=True)
                    adjusted_indices = set()
                    for idx in saved_sel_indices:
                        if isinstance(idx, int):
                            adjusted_indices.add(idx + offset)
                        else:
                            adjusted_indices.add(idx)
                    grid._sel_indices = adjusted_indices
                    print(f"DEBUG _restore: Set grid._sel_indices={adjusted_indices}", flush=True)
                    
                    # Also adjust the active cell position
                    if saved_sel_mode == "row":
                        grid._sel_row = saved_sel_row + offset
                    elif saved_sel_mode == "col":
                        grid._sel_col = saved_sel_col + offset
                
                # Clear the flag so reload() can work normally again
                grid._preserving_selection = False
                grid.viewport().update()
                print(f"DEBUG _restore: END grid._sel_indices={grid._sel_indices}", flush=True)
            except Exception as e:
                print(f"DEBUG _restore: ERROR {e}", flush=True)
                import traceback
                traceback.print_exc()
        
        print(f"DEBUG insert_dimension_items: Setting up timer for _restore", flush=True)
        try:
            QtCore.QTimer.singleShot(50, _restore)
            print(f"DEBUG insert_dimension_items: Timer set successfully", flush=True)
        except Exception as e:
            print(f"DEBUG insert_dimension_items: ERROR setting timer: {e}", flush=True)
        print(f"DEBUG insert_dimension_items: Function returning", flush=True)


    def selected_contiguous_leaf_indices(self, axis: str) -> list[int] | None:
        grid = self._grid
        if grid._sel_mode != axis:
            return None
        indices = sorted(idx for idx in grid._sel_indices if isinstance(idx, int))
        if not indices:
            return None
        entries = self._grid._rows if axis == "row" else self._grid._cols
        for idx in indices:
            if not (0 <= idx < len(entries)):
                return None
            if not entries[idx].get("is_leaf", False):
                return None
        if indices != list(range(indices[0], indices[-1] + 1)):
            return None
        return indices


