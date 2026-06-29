"""
Command Registry - Maps command IDs to implementations.

Fresh implementation - no dependencies on existing systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum, auto


class CommandCategory(Enum):
    """Command categories for organization."""
    FORMAT = auto()       # Text/cell formatting
    NAVIGATION = auto()   # View navigation
    CALCULATION = auto()  # Recalc, rule operations
    DATA = auto()         # Import, export, copy, paste
    MODEL = auto()        # Create dimensions, cubes, etc.
    VIEW = auto()         # Toggle panels, zoom
    SYSTEM = auto()       # Save, load, quit


@dataclass(frozen=True)
class CommandDef:
    """Definition of a registered command."""
    id: str                           # Unique identifier (e.g., "format.bold")
    name: str                         # Human-readable name
    category: CommandCategory         # Category for grouping
    handler: Callable[..., Any]       # Function that implements the command
    shortcut: Optional[str] = None    # Keyboard shortcut (e.g., "Ctrl+B")
    description: str = ""
    params: dict[str, type] = field(default_factory=dict)  # Param name -> type
    needs_context: bool = True        # Whether command needs execution context
    record_policy: str = "never"      # "never" | "model_mutation" | "session_replay"


class CommandRegistry:
    """
    Central registry for all application commands.
    Thread-safe singleton pattern.
    """

    _instance: Optional[CommandRegistry] = None

    def __new__(cls) -> CommandRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands: dict[str, CommandDef] = {}
            cls._instance._initialized = True
        return cls._instance

    def register(
        self,
        command_id: str,
        name: str,
        category: CommandCategory,
        handler: Callable[..., Any],
        shortcut: Optional[str] = None,
        description: str = "",
        params: Optional[dict[str, type]] = None,
        needs_context: bool = True,
        record_policy: str = "never",
    ) -> CommandDef:
        """Register a new command."""
        if command_id in self._commands:
            raise ValueError(f"Command '{command_id}' already registered")

        cmd = CommandDef(
            id=command_id,
            name=name,
            category=category,
            handler=handler,
            shortcut=shortcut,
            description=description,
            params=params or {},
            needs_context=needs_context,
            record_policy=record_policy,
        )
        self._commands[command_id] = cmd
        return cmd

    def unregister(self, command_id: str) -> Optional[CommandDef]:
        """Remove a command from the registry."""
        return self._commands.pop(command_id, None)

    def get(self, command_id: str) -> Optional[CommandDef]:
        """Look up a command by ID."""
        return self._commands.get(command_id)

    def get_all(self) -> dict[str, CommandDef]:
        """Get all registered commands."""
        return dict(self._commands)

    def get_by_category(self, category: CommandCategory) -> dict[str, CommandDef]:
        """Get all commands in a category."""
        return {
            k: v for k, v in self._commands.items()
            if v.category == category
        }

    def list_commands(self) -> list[str]:
        """List all registered command IDs."""
        return list(self._commands.keys())

    def find(self, pattern: str) -> list[CommandDef]:
        """Find commands matching a pattern (case-insensitive)."""
        pattern = pattern.lower()
        return [
            cmd for cmd in self._commands.values()
            if pattern in cmd.id.lower()
            or pattern in cmd.name.lower()
            or pattern in cmd.description.lower()
        ]

    def clear(self):
        """Clear all registered commands (useful for testing)."""
        self._commands.clear()

    def is_registered(self, command_id: str) -> bool:
        """Check if a command ID is registered."""
        return command_id in self._commands


# Module-level singleton accessor
def get_registry() -> CommandRegistry:
    """Get the global command registry."""
    return CommandRegistry()
