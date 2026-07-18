"""
REPL Command System - List, exec, info, categories, search handlers.

Commands for discovering and executing registered commands.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from lib_utils.profiler_report import format_profiler_report

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore

# Runtime import for do_restart is deferred inside the method to avoid
# a circular import chain: lib_scripting.repl_commands → lib_repl.repl_core
# → lib_repl.__init__ → lib_repl.repl_commands → lib_scripting.repl_commands


def _parse_repl_params(arg: str) -> dict:
    """Parse key=value pairs from REPL command arguments.

    Supports tuple syntax: row_key=(item1,item2)
    """
    params = {}
    if not arg:
        return params
    args = shlex.split(arg)
    for param in args:
        if '=' not in param:
            continue
        key, value = param.split('=', 1)
        # Try to parse as tuple: (a,b) or (a,)
        if value.startswith('(') and value.endswith(')'):
            inner = value[1:-1]
            if inner.endswith(','):
                inner = inner[:-1]
            parts = [p.strip() for p in inner.split(',') if p.strip()]
            params[key] = tuple(parts)
        else:
            params[key] = _parse_repl_value(value)
    return params


def _parse_repl_value(value: str):
    """Parse a string value into appropriate type."""
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            if value.lower() in ('true', 'yes'):
                return True
            elif value.lower() in ('false', 'no'):
                return False
            elif value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            return value


def _print_result(result) -> None:
    """Print a command execution result for the REPL."""
    if result.status.name == "NOT_FOUND":
        print(f"Error: Unknown command '{result.command_id}'")
    elif result.status.name == "ERROR":
        print(f"Error: {result.error}")
    elif result.status.name == "SUCCESS":
        print(f"OK ({result.duration_ms:.1f}ms)")
        if result.data:
            print(f"  Result: {result.data}")
    else:
        print(f"Result: {result.status.name}")
        if result.error:
            print(f"  Error: {result.error}")


class REPLCommandMixin:
    """Mixin for command system operations."""

    def _all_command_names(self) -> list:
        """Return REPL do_* command names plus registered command IDs."""
        names = self.get_names()
        cmds = [n[3:] for n in names if n.startswith('do_')]
        registry = getattr(self, 'registry', None)
        if registry is not None:
            cmds.extend(registry.get_all().keys())
        # Remove duplicates while preserving order
        seen = set()
        uniq = []
        for c in cmds:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        return uniq

    def completenames(self, text, *ignored):
        """Tab-completion for command names at the start of the line."""
        return [c for c in self._all_command_names() if c.startswith(text)]

    def completedefault(self, text, line, begidx, endidx):
        """Tab-completion fallback for arguments (also includes command names)."""
        return [c for c in self._all_command_names() if c.startswith(text)]

    def do_engine(self: OpenMREPLCore, arg: str):
        """
        Show engine backend type and version.
        Usage: engine [version]
        """
        session = getattr(self, "session", None)
        ctx = getattr(session, "context", None) if session else None
        engine = getattr(ctx, "engine", None) if ctx else None
        info: dict | None = None
        if engine is not None:
            info = engine.engine_info()
        elif session is not None and hasattr(session, "query"):
            try:
                info = session.query("diagnostics_engine_backend")
            except Exception:
                info = None
        if not info:
            print("No engine loaded")
            return
        backend = info.get("type", "python")
        version = info.get("version", "unknown")
        connected = info.get("connected", False)
        server_version = info.get("server_version")
        arg = (arg or "").strip().lower()
        if arg in ("version", "v"):
            print(f"Engine version: {version}")
            if server_version:
                print(f"Server version: {server_version}")
        else:
            conn_state = "connected" if connected else "disconnected"
            print(f"Engine type: {backend} ({conn_state})")
            print(f"Engine version: {version}")
            if server_version:
                print(f"Server version: {server_version}")

    def do_list(self: OpenMREPLCore, arg: str):
        """
        List available commands.
        Usage: list [category] [search_term]
        """
        args = shlex.split(arg)

        # Parse args
        category = None
        search = None

        cats = self.command_categories
        if cats is not None:
            for a in args:
                a_upper = a.upper()
                if a_upper in cats.__members__:
                    category = cats[a_upper]
                else:
                    search = a.lower()

        # Get registered commands
        if category:
            commands = self.registry.get_by_category(category)
            print(f"\n{category.name} Commands:")
        else:
            commands = self.registry.get_all()
            print("\nAll Commands:")

        # Filter registered commands by search
        if search:
            commands = {
                k: v for k, v in commands.items()
                if search in k.lower() or search in v.name.lower()
            }

        # Also get all do_* methods (REPL commands not in registry)
        repl_cmds = []
        for attr in dir(self):
            if attr.startswith('do_') and callable(getattr(self, attr)):
                cmd_name = attr[3:]
                # Skip if already in registry
                if cmd_name not in commands:
                    # Skip aliases (methods that just call another do_* method)
                    method = getattr(self, attr)
                    import inspect
                    source = inspect.getsource(method).strip()
                    # Check if it's a simple alias (returns self.do_other(args))
                    is_alias = 'return self.do_' in source and source.count('def ') == 1
                    if not is_alias:
                        # Get first line of docstring for description
                        doc = method.__doc__ or ""
                        first_line = doc.strip().split('\n')[0] if doc else ""
                        repl_cmds.append((cmd_name, first_line))

        # Filter REPL commands by search
        if search:
            repl_cmds = [(n, d) for n, d in repl_cmds if search in n.lower()]

        if not commands and not repl_cmds:
            print("  No commands found")
            return

        # Display registered commands by category
        displayed_registry = False
        cats = self.command_categories
        if cats is not None:
            for cat in cats:
                cat_cmds = [c for c in commands.values() if c.category == cat]
                if cat_cmds:
                    displayed_registry = True
                    print(f"\n  [{cat.name}]")
                    for cmd in sorted(cat_cmds, key=lambda x: x.id):
                        shortcut = f" ({cmd.shortcut})" if cmd.shortcut else ""
                        print(f"    {cmd.id:<25} {cmd.name}{shortcut}")

        # Display REPL commands (not in registry)
        if repl_cmds:
            print(f"\n  [REPL]")
            for cmd_name, desc in sorted(repl_cmds):
                desc_str = f" - {desc}" if desc else ""
                print(f"    {cmd_name:<25} {desc_str}")

    def do_info(self: OpenMREPLCore, arg: str):
        """
        Show workspace summary or detailed command info.
        Usage: info              - Workspace summary (active view, cube, dirty count)
               info <command_id> - Detailed info about a command
        """
        if not arg:
            # Workspace summary
            print("\n--- Workspace Summary ---")

            # Active view
            view_data = self.session.query("current_view")
            view_id = view_data.get("view_id") if view_data else None
            if view_id:
                detail = self.session.query("view_detail", view_id=view_id)
                view_name = detail.get("name", view_id) if detail else view_id
                print(f"  Active view:   {view_name}")
            else:
                print(f"  Active view:   (none)")

            # Active cube
            cube_data = self.session.query("current_cube")
            cube_id = cube_data.get("cube_id") if cube_data else None
            if cube_id:
                detail = self.session.query("cube_detail", cube_id=cube_id)
                cube_name = detail.get("name", cube_id) if detail else cube_id
                print(f"  Active cube:   {cube_name}")
            else:
                print(f"  Active cube:   (none)")

            # Dirty count
            try:
                dirty_data = self.session.query("diagnostics_dirty_count")
                dirty_count = dirty_data.get("dirty_count", "?") if dirty_data else "?"
                print(f"  Dirty cells:   {dirty_count}")
            except Exception:
                print(f"  Dirty cells:   (unavailable)")

            # Model counts
            views = self.session.query("view_list")
            view_count = len(views.get("views", [])) if views else 0
            cubes = self.session.query("cube_list")
            cube_count = len(cubes.get("cubes", [])) if cubes else 0
            dims = self.session.query("dimension_list")
            dim_count = len(dims.get("dimensions", [])) if dims else 0
            print(f"  Views:         {view_count}")
            print(f"  Cubes:         {cube_count}")
            print(f"  Dimensions:    {dim_count}")
            return

        cmd_id = arg.strip()
        cmd_def = self.registry.get(cmd_id)

        if cmd_def:
            # Registered command info
            print(f"\nCommand: {cmd_def.id}")
            print(f"  Name: {cmd_def.name}")
            print(f"  Category: {cmd_def.category.name}")
            print(f"  Shortcut: {cmd_def.shortcut or 'None'}")
            print(f"  Needs Context: {cmd_def.needs_context}")
            if cmd_def.description:
                print(f"  Description: {cmd_def.description}")
            if cmd_def.params:
                print(f"  Parameters:")
                for name, typ in cmd_def.params.items():
                    print(f"    - {name}: {typ.__name__}")
            return

        # Check for REPL command
        method_name = f"do_{cmd_id}"
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            if callable(method):
                doc = method.__doc__ or ""
                print(f"\nCommand: {cmd_id}")
                print(f"  Type: REPL command")
                if doc:
                    print(f"  Description: {doc.strip()}")
                return

        print(f"Error: Command '{cmd_id}' not found")

    def complete_info(self, text, line, begidx, endidx):
        """Tab-complete the argument to 'info' with all available command names."""
        return self.completedefault(text, line, begidx, endidx)

    def do_categories(self: OpenMREPLCore, arg: str):
        """List all command categories."""
        cats = self.command_categories
        if cats is None:
            print("Error: command categories not available")
            return
        print("\nCommand Categories:")
        for cat in cats:
            count = len(self.registry.get_by_category(cat))
            print(f"  {cat.name:<15} ({count} commands)")

    def do_search(self: OpenMREPLCore, arg: str):
        """
        Search for commands.
        Usage: search <pattern>
        """
        if not arg:
            print("Error: No search pattern specified")
            return

        results = self.registry.find(arg)
        if not results:
            print(f"No commands found matching '{arg}'")
            return

        print(f"\nSearch results for '{arg}':")
        for cmd in results:
            print(f"  {cmd.id:<25} {cmd.name}")

    def do_exec(self: OpenMREPLCore, arg: str):
        """
        Execute a command.
        Usage: exec <command_id> [key=value ...]
        Example: exec format.bold
                 exec data.copy selection=current
                 exec {{cmd}}
        """
        if not arg:
            print("Error: No command specified. Usage: exec <command_id>")
            return

        # Expand {{name}} macro placeholders from context variables
        import re

        def expand_macro(match):
            var_name = match.group(1)
            variables = self.session.get_variables()
            if var_name in variables:
                return str(variables[var_name])
            return match.group(0)

        arg = re.sub(r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}', expand_macro, arg)

        args = shlex.split(arg)
        command_id = args[0]

        # Parse parameters
        params = {}
        for param in args[1:]:
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = self._parse_value(value)

        result = self.session.execute(command_id, **params)

        if result.status.name == "NOT_FOUND":
            print(f"Error: Unknown command '{command_id}'")
            print("Use 'list' to see available commands")
        elif result.status.name == "ERROR":
            print(f"Error: {result.error}")
        else:
            print(f"Executed in {result.duration_ms:.1f}ms")
            if result.data:
                print(f"  Result: {result.data}")

    def do_clear(self: OpenMREPLCore, arg: str):
        """Clear the screen."""
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

    def do_quit(self: OpenMREPLCore, arg: str):
        """Exit the REPL."""
        print("Shutting down GUI...")
        self._close_gui_if_running()
        print("Goodbye!")
        return True

    def do_exit(self: OpenMREPLCore, arg: str):
        """Exit the REPL."""
        return self.do_quit(arg)

    def do_restart(self: OpenMREPLCore, arg: str):
        """
        Restart OpenM (quit and relaunch).
        Usage: restart
        """
        print("restarting OpenM...")
        self._save_history()
        from lib_repl.repl_core import OpenMREPLCore as _OpenMREPLCore
        _OpenMREPLCore.restart_requested = True
        return True

    def do_views(self: OpenMREPLCore, arg: str):
        """List all views. Usage: views"""
        data = self.session.query("view_list")
        views = data.get("views", []) if data else []
        if not views:
            print("No views")
            return
        print(f"Views ({len(views)}):")
        for v in views:
            print(f"  {v.get('name', v.get('id', '?'))}")

    def do_cubes(self: OpenMREPLCore, arg: str):
        """List all cubes. Usage: cubes"""
        data = self.session.query("cube_list")
        cubes = data.get("cubes", []) if data else []
        if not cubes:
            print("No cubes")
            return
        print(f"Cubes ({len(cubes)}):")
        for c in cubes:
            print(f"  {c.get('name', c.get('id', '?'))}")

    def do_dimensions(self: OpenMREPLCore, arg: str):
        """List all dimensions. Usage: dimensions"""
        data = self.session.query("dimension_list")
        dims = data.get("dimensions", []) if data else []
        if not dims:
            print("No dimensions")
            return
        print(f"Dimensions ({len(dims)}):")
        for d in dims:
            item_count = d.get("items", "?")
            print(f"  {d.get('name', d.get('id', '?'))} ({item_count} items)")

    def do_profilers(self: OpenMREPLCore, arg: str):
        """List registered GUI profiler endpoints. Usage: profilers"""
        data = self.session.query("profiler_list")
        if isinstance(data, list):
            endpoints = data
        elif isinstance(data, dict):
            endpoints = data.get("endpoints", [])
        else:
            endpoints = []
        if not endpoints:
            print("No GUI profiler endpoints registered")
            return
        print(f"Registered GUI profiler endpoints ({len(endpoints)}):")
        for ep in endpoints:
            if isinstance(ep, dict):
                alias = ep.get("alias", "?")
                endpoint_id = ep.get("endpoint_id", "?")
                print(f"  {alias}: {endpoint_id}")
            else:
                print(f"  {ep}")

    def do_profile(self: OpenMREPLCore, arg: str):
        """
        Profile a GUI endpoint for the given duration.
        Usage: profile gui <endpoint_id_or_alias> <seconds>
        """
        args = shlex.split(arg)
        if len(args) < 3 or args[0] != "gui":
            print("Usage: profile gui <endpoint_id_or_alias> <seconds>")
            return
        endpoint_id = args[1]
        try:
            duration_seconds = float(args[2])
        except ValueError:
            print("Error: duration must be a number")
            return
        if duration_seconds <= 0:
            print("Error: duration must be positive")
            return

        result = self.session.execute(
            "profile_gui", endpoint_id=endpoint_id, duration_seconds=duration_seconds
        )
        if result.status.name == "ERROR":
            print(f"Error: {result.error}")
            return
        if not result.data:
            print("No profile data received")
            return

        # result.data is either a snapshot dict or an error dict from the runtime command.
        if isinstance(result.data, dict) and "error" in result.data:
            print(f"Error: {result.data['error']}")
            return

        print(format_profiler_report(result.data, title=f"profile {endpoint_id} ({duration_seconds}s)"))

    def do_set_dependency_tracking(self: OpenMREPLCore, arg: str):
        """Toggle dependency tracking. Usage: set_dependency_tracking on|off"""
        enabled = arg.strip().lower() in ("on", "true", "yes", "1")
        result = self.session.execute("set_dependency_tracking", enabled=enabled)
        if result.success:
            print(f"Dependency tracking: {'ON' if enabled else 'OFF'}")
        else:
            print(f"Error: {result.error}")

    def do_set_multithread_recompute(self: OpenMREPLCore, arg: str):
        """Toggle multithreaded recalculation. Usage: set_multithread_recompute on|off"""
        enabled = arg.strip().lower() in ("on", "true", "yes", "1")
        result = self.session.execute("set_multithread_recompute", enabled=enabled)
        if result.success:
            print(f"Multithread recompute: {'ON' if enabled else 'OFF'}")
        else:
            print(f"Error: {result.error}")

    def do_cat(self: OpenMREPLCore, arg: str):
        """Alias for 'categories'."""
        return self.do_categories(arg)

    def do_ls(self: OpenMREPLCore, arg: str):
        """Alias for 'list'."""
        return self.do_list(arg)

    def do_run(self: OpenMREPLCore, arg: str):
        """Alias for 'exec'."""
        return self.do_exec(arg)

    def help_list(self: OpenMREPLCore):
        print("\nlist [category] [search]")
        print("  List available commands.")
        print("  Examples:")
        print("    list              # List all commands")
        print("    list FORMAT       # List formatting commands")
        print("    list bold         # Search for 'bold'")

    def help_exec(self: OpenMREPLCore):
        print("\nexec <command_id> [params...]")
        print("  Execute a command.")
        print("  Examples:")
        print("    exec format.bold")
        print("    exec data.copy")
        print("    exec view.zoom_in amount=2")
        print("    exec {{cmd}}  # expands {{cmd}} from context variables")

    # --- Phase 1A: Cell Value Commands ---

    def do_set_cell(self: OpenMREPLCore, arg: str):
        """
        Set a cell value by row and column indices.
        Usage: set_cell view_id=<id> row=<n> col=<n> value=<value>
        """
        params = _parse_repl_params(arg)
        # Wrap legacy row/col params into canonical cell_ref
        row = params.pop("row", None)
        col = params.pop("col", None)
        if row is not None and col is not None:
            params["cell_ref"] = {"kind": "index", "value": {"row": row, "col": col}}
        result = self.session.execute("set_cell_hardvalue", **params)
        _print_result(result)

    def help_set_cell(self: OpenMREPLCore):
        print("\nset_cell view_id=<id> row=<n> col=<n> value=<value>")
        print("  Set a cell value by row/column indices.")
        print("  Example: set_cell view_id=view_1 row=0 col=0 value=42")

    def do_set_cell_by_keys(self: OpenMREPLCore, arg: str):
        """
        Set a cell value by dimension item keys.
        Usage: set_cell_by_keys view_id=<id> row_key=(<id>,) col_key=(<id>,) value=<value>
        """
        params = _parse_repl_params(arg)
        # Wrap legacy row_key/col_key params into canonical cell_ref
        row_key = params.pop("row_key", None)
        col_key = params.pop("col_key", None)
        if row_key is not None and col_key is not None:
            params["cell_ref"] = {"kind": "keys", "value": {"row_key": list(row_key), "col_key": list(col_key)}}
        result = self.session.execute("set_cell_hardvalue", **params)
        _print_result(result)

    def help_set_cell_by_keys(self: OpenMREPLCore):
        print("\nset_cell_by_keys view_id=<id> row_key=(<id>,) col_key=(<id>,) value=<value>")
        print("  Set a cell value by dimension item keys.")
        print("  Example: set_cell_by_keys view_id=view_1 row_key=(item1,) col_key=(item2,) value=42")

    def do_clear_cell(self: OpenMREPLCore, arg: str):
        """
        Clear a cell value by row and column indices.
        Usage: clear_cell view_id=<id> row=<n> col=<n>
        """
        params = _parse_repl_params(arg)
        row = params.pop("row", None)
        col = params.pop("col", None)
        if row is not None and col is not None:
            params["cell_ref"] = {"kind": "index", "value": {"row": row, "col": col}}
        result = self.session.execute("clear_cell_hardvalue", **params)
        _print_result(result)

    def help_clear_cell(self: OpenMREPLCore):
        print("\nclear_cell view_id=<id> row=<n> col=<n>")
        print("  Clear a cell value by row/column indices.")
        print("  Removes the direct stored value/override. Does NOT delete anchored rules.")
        print("  Example: clear_cell view_id=view_1 row=0 col=0")

    def do_clear_cell_by_keys(self: OpenMREPLCore, arg: str):
        """
        Clear a cell value by dimension item keys.
        Usage: clear_cell_by_keys view_id=<id> row_key=(<id>,) col_key=(<id>,)
        """
        result = self.session.execute("clear_cell_by_keys", **_parse_repl_params(arg))
        _print_result(result)

    def help_clear_cell_by_keys(self: OpenMREPLCore):
        print("\nclear_cell_by_keys view_id=<id> row_key=(<id>,) col_key=(<id>,)")
        print("  Clear a cell value by dimension item keys.")
        print("  Removes the direct stored value/override. Does NOT delete anchored rules.")
        print("  Example: clear_cell_by_keys view_id=view_1 row_key=(item1,) col_key=(item2,)")
