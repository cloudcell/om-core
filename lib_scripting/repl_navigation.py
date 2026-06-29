"""
REPL Navigation - Selection, movement, grid navigation.

Commands for navigating and selecting cells in the grid.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore


class REPLNavigationMixin:
    """Mixin for navigation and selection operations."""

    def do_right(self: OpenMREPLCore, arg: str):
        """Move selection right. Usage: right [steps]"""
        steps = int(arg) if arg.isdigit() else 1
        self._navigate_selection("right", steps)

    def do_down(self: OpenMREPLCore, arg: str):
        """Move selection down. Usage: down [steps]"""
        steps = int(arg) if arg.isdigit() else 1
        self._navigate_selection("down", steps)

    def do_left(self: OpenMREPLCore, arg: str):
        """Move selection left. Usage: left [steps]"""
        steps = int(arg) if arg.isdigit() else 1
        self._navigate_selection("left", steps)

    def do_up(self: OpenMREPLCore, arg: str):
        """Move selection up. Usage: up [steps]"""
        steps = int(arg) if arg.isdigit() else 1
        self._navigate_selection("up", steps)

    def _navigate_selection(self: OpenMREPLCore, direction: str, steps: int = 1, sync: bool = True):
        """Navigate selection through the command spine.

        Routes move_selection through session.execute for both local and remote.
        """
        result = self.session.execute("move_selection", direction=direction, amount=steps)
        if result.success:
            pos = result.data.get("position")
            if pos:
                self._sel_row, self._sel_col = pos
                print(f"Moved {direction} to ({pos[0]}, {pos[1]})")
            else:
                print(f"Moved {direction}")
        else:
            print(f"Error navigating: {result.error}")

    def do_selection(self: OpenMREPLCore, arg: str):
        """
        Show current selection info through the query spine.
        Usage: selection
        """
        data = self.session.query("selection_current")
        if data and data.get("type") == "selection_current":
            cursor = data.get("cursor", (0, 0))
            print(f"Selection: ({cursor[0]}, {cursor[1]})")
            return []
        print("Error: could not read selection from session")
        return []

    def do_select(self: OpenMREPLCore, arg: str):
        """
        Select a cell or range by row and column indices.
        Usage: select <row> <col>          # Single cell
               select <r1> <c1> <r2> <c2>  # Range/region
        """
        if not arg:
            print("Usage: select <row> <col> or select <r1> <c1> <r2> <c2>")
            return

        args = arg.strip().split()
        if len(args) not in (2, 4):
            print("Usage: select <row> <col> or select <r1> <c1> <r2> <c2>")
            return

        try:
            coords = [int(a) for a in args]
        except ValueError:
            print("Error: coordinates must be integers")
            return

        if len(coords) == 2:
            row1, col1 = coords[0], coords[1]
            row2, col2 = coords[0], coords[1]
        else:
            row1, col1, row2, col2 = coords
            row1, row2 = min(row1, row2), max(row1, row2)
            col1, col2 = min(col1, col2), max(col1, col2)

        result = self.session.execute("set_selection", row=row2, col=col2)
        if result.success:
            pos = result.data.get("position")
            self._sel_row, self._sel_col = pos
            if len(args) == 2:
                print(f"Selected cell ({pos[0]}, {pos[1]})")
            else:
                print(f"Selected range ({row1}, {col1}) to ({row2}, {col2})")
        else:
            print(f"Error: {result.error}")

    def _get_selection_data(self: OpenMREPLCore):
        """Get current selection data for command substitution.

        Returns a dict with cube_name, mode, count, and addresses.
        Uses the GUI port when available for real selection state;
        falls back to engine-only introspection when running headless.
        """
        # Try GUI port first for real selection
        if getattr(self, 'gui_port', None):
            addresses = self.gui_port.selection_addresses()
            if addresses:
                # Derive cube name from first address
                cube_name = addresses[0].split('::', 1)[0] if addresses else None
                return {
                    'cube_name': cube_name,
                    'mode': 'cell',
                    'count': len(addresses),
                    'addresses': addresses,
                    'view_id': None,
                }

        # Fallback: query-based headless mode (no engine access)
        view_id = None
        try:
            result = self.session.query("current_view")
            if result:
                view_id = result.get("view_id")
        except Exception:
            pass

        cube_id = None
        cube_name = None
        if view_id:
            try:
                view_data = self.session.query("view_detail", view_id=view_id)
                if view_data:
                    cube_id = view_data.get("cube_id")
                    cube_name = view_data.get("name")
            except Exception:
                pass
        if not cube_id:
            try:
                cube_list = self.session.query("cube_list")
                cubes = cube_list.get("cubes", []) if cube_list else []
                if cubes:
                    cube_id = cubes[0].get("id")
                    cube_name = cubes[0].get("name")
            except Exception:
                pass

        return {
            'cube_name': cube_name,
            'mode': 'cell',
            'count': 0,
            'addresses': [],
            'view_id': view_id,
        }
