"""Headless macro playback runner.

Provides a REPL-compatible command surface for macro replay without
inheriting from cmd.Cmd or owning GUI widgets.  All semantic actions
route through the command spine via CommandSession.
"""

from __future__ import annotations

from typing import Any

# Scripting mixins provide the do_* command surface.  We compose them over a
# headless base so macro playback stays compatible without pulling in
# cmd.Cmd, readline history, or GUI state.
from lib_scripting import (
    REPLScriptingMixin,
    REPLControlFlowMixin,
    REPLUDFMixin,
    REPLNavigationMixin,
    REPLHelpMixin,
    REPLRecordingMixin,
    REPLFileMixin,
    REPLModelMixin,
    REPLCommandMixin,
)


class _HeadlessCommandBase:
    """Minimal base providing the attributes REPL mixins expect.

    No cmd.Cmd, no readline, no atexit, no StatusDisplay subscriber.
    """

    def __init__(
        self,
        session: Any,
        script_parser_module: Any = None,
    ):
        if session is None:
            raise TypeError("_HeadlessCommandBase requires a session argument")

        self.script_parser_module = script_parser_module

        self._sel_row: int | None = None
        self._sel_col: int | None = None
        self.gui_window: Any = None
        self.gui_thread: Any = None
        self.gui_app: Any = None
        self.gui_exit_event: Any = None
        self.gui_port: Any = None

        self.session = session

    @property
    def variables(self) -> dict:
        return self.session.get_variables()

    @property
    def global_vars(self) -> dict:
        return self.session.get_global_vars()

    # Stubs for methods that mixins (or play_macro) may call.
    def _show_status(self, msg: str) -> None:
        pass

    def _load_history(self) -> None:
        pass

    def _save_history(self) -> None:
        pass

    def _close_gui_if_running(self) -> None:
        pass

    def _drain_output_queue(self) -> None:
        pass

    # --- cmd.Cmd compatibility stubs ---
    def parseline(self, line: str):
        """Mimic cmd.Cmd.parseline for REPLScriptingMixin.onecmd()."""
        line = line.strip()
        if not line:
            return None, None, line
        if line.startswith('#'):
            return None, None, line
        parts = line.split(None, 1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ''
        return cmd, arg, line

    def onecmd(self, line: str):
        """Delegate to ScriptLineExecutor for shared script-line semantics."""
        from lib_scripting.line_executor import ScriptLineExecutor
        return ScriptLineExecutor(self).execute_line(line)


class MacroPlaybackRunner(
    REPLScriptingMixin,
    REPLControlFlowMixin,
    REPLUDFMixin,
    REPLNavigationMixin,
    REPLHelpMixin,
    REPLRecordingMixin,
    REPLFileMixin,
    REPLModelMixin,
    REPLCommandMixin,
    _HeadlessCommandBase,
):
    """Headless runner for macro playback without GUI coupling.

    Provides the same ``do_*`` interface as ``OpenMREPL`` for macro
    compatibility, but does not inherit from ``cmd.Cmd`` and does not
    own GUI widgets, grid state, or selection state.

    Usage::

        runner = MacroPlaybackRunner(session=client_session)
        errors = recorder.play_macro("my_macro", runner)
    """

    pass
