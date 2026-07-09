"""
lib_command.commands - Command implementations by domain

Property-based command implementations organized by category:
- format: Cell formatting (bold, color, font, etc.)
- data: Data operations (value, rule body)
- model: Model CRUD (create, delete dimensions, cubes, items)
- navigation: View navigation
- system: System operations (save, load, recalc, quit)
- query: Read-only state queries
- rule: Rule management
"""

from .format import cmd_set_format, PropertySpec, list_properties, PROPERTY_REGISTRY
from .data import cmd_set_data, cmd_set_value, cmd_set_rule_body
from .model import cmd_create, cmd_delete, cmd_delete_dimension_items
from .navigation import cmd_navigate
from .system import (
    cmd_recalc, cmd_save, cmd_load, cmd_quit, cmd_cancel_recalc,
    cmd_set_dependency_tracking, cmd_set_multithread_recompute, cmd_clear_profiler_snapshot,
    cmd_clear_cache, cmd_undo, cmd_redo,
)
from .rule import cmd_rule
from .query import cmd_query
from .profiler_register import (
    cmd_profiler_register,
    cmd_profiler_unregister,
    query_profiler_list,
    resolve_profiler_endpoint,
)
from .profile_gui import cmd_profile_gui, clear_pending_profile_requests
from .profiler_report import cmd_profiler_report
from .timeline import (
    cmd_checkpoint,
    cmd_restore,
    cmd_rename_checkpoint,
    cmd_delete_checkpoint,
)

# Main set command dispatcher
from .dispatcher import cmd_set

__all__ = [
    # Dispatcher
    "cmd_set",
    # Format
    "cmd_set_format", "PropertySpec", "list_properties", "PROPERTY_REGISTRY",
    # Data
    "cmd_set_data", "cmd_set_value", "cmd_set_rule_body",
    # Model
    "cmd_create", "cmd_delete", "cmd_delete_dimension_items",
    # Navigation
    "cmd_navigate",
    # System
    "cmd_recalc", "cmd_save", "cmd_load", "cmd_quit",
    "cmd_cancel_recalc", "cmd_set_dependency_tracking",
    "cmd_set_multithread_recompute", "cmd_clear_profiler_snapshot",
    "cmd_clear_cache", "cmd_undo", "cmd_redo",
    # Rule
    "cmd_rule",
    # Query
    "cmd_query",
    # Profiler
    "cmd_profiler_register",
    "cmd_profiler_unregister",
    "query_profiler_list",
    "resolve_profiler_endpoint",
    "cmd_profile_gui",
    "clear_pending_profile_requests",
    "cmd_profiler_report",
    # Timeline
    "cmd_checkpoint",
    "cmd_restore",
    "cmd_rename_checkpoint",
    "cmd_delete_checkpoint",
]