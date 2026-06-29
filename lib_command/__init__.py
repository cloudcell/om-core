"""
lib_command - Command execution system for OpenM

Property-based design: Most operations are 'set' commands on targets.
Provides unified interface for GUI, CLI/REPL, and scripting.

Organized into subsystems:
- core: Registry and execution infrastructure
- commands: Domain-specific command implementations
- interfaces: CLI and REPL entry points
- support: Help system and macro recording
"""

# Core exports
from .core.registry import CommandRegistry, CommandDef, get_registry, CommandCategory
from .core.executor import CommandExecutor, ExecutionResult, ExecutionContext, get_executor
from .core.session import CommandSession
from .core.session_store import SessionStore, SessionRecord, get_session_store
from .core.session_manager import SessionManager, get_session_manager
from .core.session_gateway import SessionGateway, get_session_gateway
from .core.bootstrap import register_default_commands, init_command_services, teardown_command_services
from .core.script_parser import parse_script, execute_script, ScriptLexer, ScriptParser

# Commands exports
from .commands import (
    cmd_set, cmd_navigate, cmd_create, cmd_delete,
    cmd_recalc, cmd_save, cmd_load, cmd_quit,
    PropertySpec, list_properties, PROPERTY_REGISTRY
)

# Interface exports
from .interfaces.cli import main as cli_main

# Support exports
from .support.help_system import get_help, HandbookHelp, HandbookSection
from .support.macro_recorder import get_recorder, MacroRecorder, Macro, MacroCommand

__all__ = [
    # Core
    "CommandRegistry", "CommandDef", "get_registry", "CommandCategory",
    "CommandExecutor", "ExecutionResult", "ExecutionContext", "get_executor",
    "CommandSession",
    "SessionStore", "SessionRecord", "get_session_store",
    "SessionManager", "get_session_manager",
    "SessionGateway", "get_session_gateway",
    "register_default_commands",
    "parse_script", "execute_script", "ScriptLexer", "ScriptParser",
    # Commands
    "cmd_set", "cmd_navigate", "cmd_create", "cmd_delete",
    "cmd_recalc", "cmd_save", "cmd_load", "cmd_quit",
    "PropertySpec", "list_properties", "PROPERTY_REGISTRY",
    # Interfaces
    "cli_main",
    # Support
    "get_help", "HandbookHelp", "HandbookSection",
    "get_recorder", "MacroRecorder", "Macro", "MacroCommand",
]
