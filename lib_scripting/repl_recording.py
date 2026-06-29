"""
REPL Recording - Macro recording and playback.

Commands for recording, playing, and managing macros.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore


class REPLRecordingMixin:
    """Mixin for recording and playback operations."""

    def do_record(self: OpenMREPLCore, arg: str):
        """
        Record and play macros.
        Usage: record <action> [args]

        Actions:
          start <name> [desc]  - Start recording a macro
          stop                 - Stop recording
          play <name>          - Play back a macro
          list                 - List saved macros
          delete <name>        - Delete a macro
          info                 - Show current recording status

        Examples:
          record start format_blue "Apply blue background"
          format bg_color #3B82F6
          format font_size 14
          record stop
          record play format_blue
        """
        from lib_utils.macro_recorder import get_recorder
        recorder = get_recorder()

        if not arg:
            print(self.do_record.__doc__)
            return

        parts = arg.split(maxsplit=1)
        action = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        if action == "start":
            if not rest:
                print("Error: Macro name required. Usage: record start <name> [description]")
                return
            name_parts = rest.split(maxsplit=1)
            name = name_parts[0]
            desc = name_parts[1] if len(name_parts) > 1 else ""
            if recorder.start_recording(name, desc):
                print(f"Recording macro '{name}'...")
            else:
                print("Error: Already recording. Stop first with: record stop")

        elif action == "stop":
            macro = recorder.stop_recording()
            if macro:
                print(f"Saved macro '{macro.name}' ({len(macro.commands)} commands)")
            else:
                print("Error: Not currently recording")

        elif action == "info":
            info = recorder.get_recording_info()
            if info:
                print(f"Recording: {info['name']}")
                print(f"  Commands: {info['commands']}")
                print(f"  Duration: {info['duration']:.1f}s")
            else:
                print("Not currently recording")

        elif action == "play":
            if not rest:
                print("Error: Macro name required. Usage: record play <name>")
                return
            errors = recorder.play_macro(rest, self)
            if errors:
                for err in errors:
                    print(f"  {err}")
            else:
                print(f"Macro '{rest}' completed")

        elif action == "list":
            macros = recorder.list_macros()
            if not macros:
                print("No saved macros")
                return
            print("Saved macros:")
            for m in macros:
                print(f"  {m['name']}: {m['commands']} cmds - {m.get('description', '')}")

        elif action == "delete":
            if not rest:
                print("Error: Macro name required. Usage: record delete <name>")
                return
            if recorder.delete_macro(rest):
                print(f"Deleted macro '{rest}'")
            else:
                print(f"Macro '{rest}' not found")
        else:
            print(f"Unknown action: {action}")
            print(self.do_record.__doc__)

    def do_play(self: OpenMREPLCore, arg: str):
        """
        Play a recorded macro with timing.
        Usage: play <recording_file> [--realtime]
        Example: play recording_20260503_074900.openm
                 play my_macro.openm --realtime  # Respect original timing
        """
        if not arg:
            print("Usage: play <recording_file> [--realtime]")
            return

        args = arg.strip().split()
        filename = args[0]
        realtime = '--realtime' in args or '-r' in args

        from lib_utils.paths import OM_RECORDINGS_DIR
        filepath = Path(filename)
        if not filepath.is_absolute():
            filepath = OM_RECORDINGS_DIR / filename

        if not filepath.exists():
            print(f"Recording not found: {filepath}")
            return

        try:
            with open(filepath, 'r') as f:
                content = f.read()

            commands = []
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    delay = 1.0 if realtime else 0
                    commands.append((line, delay))

            print(f"Playing {len(commands)} commands from {filepath.name}")
            if realtime:
                print("Realtime mode: executing with delays")

            for i, (cmd, delay) in enumerate(commands):
                if realtime and i > 0:
                    time.sleep(delay)
                else:
                    time.sleep(0.15)
                print(f"  > {cmd}")
                try:
                    if '=' in cmd and '$(' in cmd:
                        print(f"  [skip variable assignment: {cmd}]")
                        continue
                    self.onecmd(cmd)
                except Exception as e:
                    print(f"  [error: {e}]")
                    continue

            print(f"Playback complete")
            time.sleep(0.2)

        except Exception as e:
            print(f"Error playing recording: {e}")

        return False

    # Backward compatibility with old GUI recording system
    def _start_recording(self: OpenMREPLCore, filename: str | None = None):
        """Start recording GUI actions (legacy support)."""
        if hasattr(self, '_recording') and self._recording:
            print("Already recording")
            return

        self._recording = True
        self._recorded_actions = []
        self._record_start_time = time.time()
        self._record_filename = filename

        if hasattr(self, 'gui_port') and self.gui_port:
            self.gui_port.connect_selection_recording(
                self._on_selection_changed,
                self._on_cell_value_changed,
            )
            print("Recording started. Actions will be captured.")
        else:
            print("Warning: No GUI port found, recording may not capture all actions")

    def _stop_recording(self: OpenMREPLCore):
        """Stop recording and save (legacy support)."""
        if not hasattr(self, '_recording') or not self._recording:
            print("Not currently recording")
            return

        self._recording = False

        if hasattr(self, 'gui_port') and self.gui_port:
            self.gui_port.disconnect_selection_recording(self._on_selection_changed)

        if self._recorded_actions:
            custom_filename = getattr(self, '_record_filename', None)
            if custom_filename:
                if not custom_filename.endswith('.openm'):
                    custom_filename += '.openm'
                filename = custom_filename
            else:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{timestamp}.openm"
            from lib_utils.paths import OM_RECORDINGS_DIR
            filepath = OM_RECORDINGS_DIR / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'w') as f:
                f.write("# OpenModeling GUI Recording\n")
                f.write(f"# Started: {time.ctime(self._record_start_time)}\n")
                f.write(f"# Duration: {time.time() - self._record_start_time:.1f}s\n\n")

                for action in self._recorded_actions:
                    f.write(f"# {action['time']:.2f}s: {action['desc']}\n")
                    if action['cmd']:
                        f.write(f"{action['cmd']}\n\n")

            print(f"Recording saved to {filepath}")
            print(f"Captured {len(self._recorded_actions)} actions")
        else:
            print("No actions recorded")

    def _recording_status(self: OpenMREPLCore):
        """Show recording status (legacy support)."""
        if hasattr(self, '_recording') and self._recording:
            elapsed = time.time() - self._record_start_time
            count = len(self._recorded_actions)
            print(f"Recording: ACTIVE ({elapsed:.1f}s, {count} actions)")
        else:
            print("Recording: STOPPED")

    def _on_selection_changed(self: OpenMREPLCore):
        """Callback when selection changes in GUI."""
        if not hasattr(self, '_recording') or not self._recording:
            return

        if not getattr(self, 'gui_port', None):
            return

        selection = self.gui_port.recording_selection()
        if selection is None:
            return
        row, col = selection
        elapsed = time.time() - self._record_start_time

        action = {
            'time': elapsed,
            'desc': f"Selected cell ({row}, {col})",
            'cmd': f"select {row} {col}"
        }
        self._recorded_actions.append(action)
        print(f"[record] {action['desc']}")

    def _on_cell_value_changed(self: OpenMREPLCore, row: int, col: int, value: str):
        """Callback when cell value changes in GUI."""
        if not hasattr(self, '_recording') or not self._recording:
            return

        elapsed = time.time() - self._record_start_time
        action = {
            'time': elapsed,
            'desc': f"Entered value at ({row}, {col}): {value!r}",
            'cmd': f"enter {row} {col} {value}"
        }
        self._recorded_actions.append(action)
        print(f"[record] {action['desc']}")
