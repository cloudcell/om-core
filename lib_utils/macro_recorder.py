"""Macro recording and playback for OpenModeling REPL.

Macros are stored as plain text .openm files for human readability and editability.

Format:
    # Macro: <name>
    # Created: <ISO timestamp>
    # Description: <description>
    # Expand: true|false (optional, defaults to false)
    
    <command> <args>
    <command> <args>
    ...

Usage:
    record start <name> [description]          # Start unexpanded (dynamic) recording
    record start --expand <name> [description] # Start expanded (static) recording
    record stop                                # Stop recording
    list macros                                # List saved macros
    play <name>                                # Play back a macro
    play <name> --preserve-vars                # Play with variables preserved
    delete <name>                              # Delete a macro
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MacroCommand:
    """A single recorded command."""
    command: str
    args: str


@dataclass
class Macro:
    """A recorded macro with metadata."""
    name: str
    created: float
    commands: list[MacroCommand] = field(default_factory=list)
    description: str = ""
    # True = recorded with --expand, stored actual values
    # False = unexpanded, stores variable references for dynamic playback
    expand_mode: bool = False

    def to_text(self) -> str:
        """Convert macro to plain text format."""
        lines = [
            f"# Macro: {self.name}",
            f"# Created: {datetime.fromtimestamp(self.created).isoformat()}",
        ]
        if self.description:
            lines.append(f"# Description: {self.description}")
        if self.expand_mode:
            lines.append("# Expand: true")
        lines.append("")  # Blank line before commands
        
        for cmd in self.commands:
            if cmd.args:
                lines.append(f"{cmd.command} {cmd.args}")
            else:
                lines.append(cmd.command)
        
        return "\n".join(lines)

    @classmethod
    def from_text(cls, name: str, text: str) -> "Macro":
        """Parse macro from plain text format."""
        lines = text.strip().split("\n")
        
        description = ""
        created = time.time()
        expand_mode = False
        commands: list[MacroCommand] = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                # Parse header comments
                if line.startswith("# Description:"):
                    description = line.split(":", 1)[1].strip()
                elif line.startswith("# Created:"):
                    try:
                        created_str = line.split(":", 1)[1].strip()
                        created = datetime.fromisoformat(created_str).timestamp()
                    except Exception:
                        pass
                elif line.startswith("# Expand: true"):
                    expand_mode = True
                continue
            
            # Parse command line
            parts = line.split(None, 1)
            if parts:
                cmd = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                commands.append(MacroCommand(command=cmd, args=args))
        
        return cls(
            name=name,
            created=created,
            description=description,
            commands=commands,
            expand_mode=expand_mode
        )


class MacroRecorder:
    """Records and manages REPL macros."""

    from lib_utils.paths import OM_MACROS_DIR

    MACROS_DIR = OM_MACROS_DIR

    def __init__(self) -> None:
        self._recording: Macro | None = None
        self._start_time: float = 0.0
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.MACROS_DIR.mkdir(parents=True, exist_ok=True)

    def start_recording(
        self,
        name: str,
        description: str = "",
        expand: bool = False,
    ) -> bool:
        """Start recording a new macro.
        
        Args:
            name: Macro name
            description: Human-readable description
            expand: If True, records expanded values (cell addresses).
                   If False (default), records variable references (dynamic).
        """
        if self._recording:
            return False
        self._recording = Macro(
            name=name,
            created=time.time(),
            description=description,
            expand_mode=expand
        )
        self._start_time = time.time()
        return True

    def stop_recording(self) -> Macro | None:
        """Stop recording and return the macro."""
        if not self._recording:
            return None
        macro = self._recording
        self._recording = None
        self._save_macro(macro)
        return macro

    def record_command(self, command: str, args: str) -> None:
        """Record a command if currently recording."""
        if self._recording:
            self._recording.commands.append(
                MacroCommand(command=command, args=args)
            )

    def record_canonical(self, command_id: str, params: dict) -> None:
        """Record a canonical command with resolved params from the command spine.

        Serializes params as a simple space-separated argument string.
        """
        if not self._recording:
            return
        args_parts = []
        for key, value in params.items():
            if isinstance(value, str):
                if ' ' in value:
                    args_parts.append(f'{key}="{value}"')
                else:
                    args_parts.append(f'{key}={value}')
            else:
                args_parts.append(f'{key}={value}')
        args_str = " ".join(args_parts)
        self._recording.commands.append(
            MacroCommand(command=command_id, args=args_str)
        )

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording is not None

    def get_recording_info(self) -> dict | None:
        """Get info about current recording."""
        if not self._recording:
            return None
        return {
            "name": self._recording.name,
            "commands": len(self._recording.commands),
            "duration": time.time() - self._start_time,
            "expand_mode": self._recording.expand_mode,
        }

    def _macro_path(self, name: str) -> Path:
        return self.MACROS_DIR / f"{name}.openm"

    def _save_macro(self, macro: Macro) -> None:
        path = self._macro_path(macro.name)
        with open(path, "w") as f:
            f.write(macro.to_text())

    def load_macro(self, name: str) -> Macro | None:
        """Load a macro by name."""
        path = self._macro_path(name)
        if not path.exists():
            return None
        with open(path) as f:
            return Macro.from_text(name, f.read())

    def list_macros(self) -> list[dict]:
        """List all saved macros with metadata."""
        macros = []
        paths = sorted(self.MACROS_DIR.glob("*.openm"))
        for path in paths:
            try:
                macro = self.load_macro(path.stem)
                if macro:
                    macros.append({
                        "name": macro.name,
                        "created": macro.created,
                        "commands": len(macro.commands),
                        "description": macro.description,
                        "expand_mode": macro.expand_mode,
                    })
            except Exception:
                pass
        return sorted(macros, key=lambda m: m["created"], reverse=True)

    def delete_macro(self, name: str) -> bool:
        """Delete a macro. Returns True if deleted."""
        path = self._macro_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def play_macro(
        self,
        name: str,
        repl_instance,
        preserve_vars: bool = False,
        context_values: dict[str, Any] | None = None,
    ) -> list[str]:
        """Play back a macro through the given REPL instance.

        Args:
            name: Macro name to play
            repl_instance: REPL instance to execute commands through
            preserve_vars: If True, preserves current REPL variables.
                          If False, clears variables before playback and
                          restores them after (so macro references resolve fresh).
            context_values: Optional dict of variables to inject into the REPL
                          before playback (e.g. widget values for macros).

        Returns:
            List of errors, empty if successful.
        """
        try:
            import readline
        except ImportError:
            readline = None

        macro = self.load_macro(name)
        if not macro:
            return [f"Macro '{name}' not found"]

        # Use REPL variables property (works in both local and remote mode)
        variables = repl_instance.variables

        # Save current variable state
        saved_vars = dict(variables)

        if not preserve_vars:
            # Clear variables so macro references resolve fresh
            variables.clear()

        # Inject context values before playback
        if context_values:
            variables.update(context_values)

        # Disable history writes during playback (readline is unavailable on Windows)
        _orig_add_history = None
        if readline is not None:
            _orig_add_history = readline.add_history
            readline.add_history = lambda *a, **kw: None  # no-op

        # skip_history is local-only; remote mode readline is not shared
        if hasattr(repl_instance, "session") and hasattr(repl_instance.session, "context"):
            repl_instance.session.context.skip_history = True

        errors = []
        try:
            for i, cmd in enumerate(macro.commands):
                try:
                    # Reconstruct the full command line and run through onecmd
                    # so variable assignments, {{...}} expansion, and all onecmd
                    # logic are applied consistently.
                    full_line = f"{cmd.command} {cmd.args}".strip()
                    repl_instance.onecmd(full_line)
                except Exception as e:
                    errors.append(f"Error in {cmd.command}: {e}")
        finally:
            # Restore variables
            variables.clear()
            variables.update(saved_vars)
            # Restore history writes
            if hasattr(repl_instance, "session") and hasattr(repl_instance.session, "context"):
                repl_instance.session.context.skip_history = False
            if readline is not None and _orig_add_history is not None:
                readline.add_history = _orig_add_history

        return errors


# Global instance for REPL use
_macro_recorder = MacroRecorder()


def get_recorder() -> MacroRecorder:
    """Get the global macro recorder instance."""
    return _macro_recorder
