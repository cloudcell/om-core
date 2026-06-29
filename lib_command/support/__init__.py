"""
lib_command.support - Auxiliary systems

Help system and macro recording functionality.
"""

from .help_system import HandbookHelp, HandbookSection, get_help
from .macro_recorder import MacroRecorder, Macro, MacroCommand, get_recorder

__all__ = [
    "HandbookHelp", "HandbookSection", "get_help",
    "MacroRecorder", "Macro", "MacroCommand", "get_recorder",
]
