"""
lib_command.core - Core command infrastructure

Provides the foundational registry and execution systems.
"""

from .registry import CommandRegistry, CommandDef, get_registry, CommandCategory
from .executor import CommandExecutor, ExecutionResult, ExecutionContext, get_executor
from .session import CommandSession
from .session_store import SessionStore, SessionRecord, get_session_store
from .session_manager import SessionManager, get_session_manager
from .session_gateway import SessionGateway, get_session_gateway
from .query_service import QueryService
from .recorder import Recorder, Recording, RecordingSummary, RecordedMessage
from .debug_monitor import DebugMonitor, TraceEntry
from .bootstrap import register_default_commands

__all__ = [
    "CommandRegistry", "CommandDef", "get_registry", "CommandCategory",
    "CommandExecutor", "ExecutionResult", "ExecutionContext", "get_executor",
    "CommandSession",
    "SessionStore", "SessionRecord", "get_session_store",
    "SessionManager", "get_session_manager",
    "SessionGateway", "get_session_gateway",
    "QueryService",
    "Recorder", "Recording", "RecordingSummary", "RecordedMessage",
    "DebugMonitor", "TraceEntry",
    "register_default_commands",
]
