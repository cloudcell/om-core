"""
lib_command.interfaces - User-facing entry points

CLI interface and compatibility re-exports for the command system.
REPL code has moved to lib_repl/.
"""

from .cli import main as cli_main

__all__ = [
    "cli_main",
]
