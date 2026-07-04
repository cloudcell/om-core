"""
REPL File Operations - Load, save, source, import.

Commands for file I/O and batch processing.
"""

from __future__ import annotations

import glob
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore


class REPLFileMixin:
    """Mixin for file I/O operations."""

    def do_load(self: OpenMREPLCore, arg: str):
        """
        Load data, macros, or models from file.
        Usage: load <type> <filepath> [options]

        Types:
          macro <filepath> [--play]  - Load macro commands
          model <filepath>           - Load workspace/model
          data <filepath>            - Import data (Excel/CSV)

        Examples:
          load macro my_macro.json
          load macro ~/macros/format.json --play
          load model ~/models/finance.openm
          load data ~/data/sales.xlsx
        """
        if not arg:
            print(self.do_load.__doc__)
            return

        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            print("Error: Usage: load <type> <filepath>")
            return

        load_type, rest = parts[0], parts[1]

        if load_type == "macro":
            self._load_macro(rest)
        elif load_type == "model":
            self._load_model(rest)
        elif load_type == "data":
            self._load_data(rest)
        else:
            print(f"Unknown type: {load_type}")
            print(f"Supported: macro, model, data")

    def complete_load(self: OpenMREPLCore, text: str, line: str, begidx: int, endidx: int):
        """Tab completion for load command."""
        import os
        from pathlib import Path

        parts = line[:endidx].split()

        if len(parts) <= 1 or (len(parts) == 2 and not line.endswith(' ')):
            types = ['macro', 'model', 'data']
            if text:
                return [t for t in types if t.startswith(text)]
            return types

        if len(parts) >= 2:
            if line.endswith(' '):
                partial = ''
            else:
                partial = parts[-1] if len(parts) > 1 else ''

            if partial.startswith('~'):
                partial = os.path.expanduser(partial)

            if not partial:
                pattern = '*'
            elif partial == '.' or partial == './':
                pattern = './*'
            elif partial.endswith('/'):
                pattern = partial + '*'
            else:
                if os.path.isdir(partial):
                    pattern = partial + '/*'
                else:
                    pattern = partial + '*'

            try:
                matches = glob.glob(pattern)
                matches = [m for m in matches if m not in ('.', './')]
                results = []
                for m in matches:
                    if m.startswith('./'):
                        m = m[2:]
                    if os.path.isdir(m) and not m.endswith('/'):
                        results.append(m + '/')
                    else:
                        results.append(m)
                return results
            except Exception:
                return []

        return []

    def _load_macro(self: OpenMREPLCore, arg: str):
        """Load macro from file."""
        parts = arg.split()
        filepath = parts[0]
        play_immediately = '--play' in parts

        from lib_utils.macro_recorder import Macro, MacroRecorder

        path = Path(filepath).expanduser()
        if not path.exists():
            print(f"File not found: {path}")
            return

        try:
            import json
            with open(path) as f:
                data = json.load(f)

            macro = Macro.from_dict(data)
            recorder = MacroRecorder()
            recorder._save_macro(macro)

            print(f"Loaded macro '{macro.name}' ({len(macro.commands)} commands)")

            if play_immediately:
                from lib_utils.macro_recorder import get_recorder
                errors = get_recorder().play_macro(macro.name, self)
                if errors:
                    for err in errors:
                        print(f"  {err}")
                else:
                    print(f"Macro '{macro.name}' executed")

        except Exception as e:
            print(f"Error loading macro: {e}")

    def _load_model(self: OpenMREPLCore, arg: str):
        """Load workspace/model from file.

        Phase 5: Uses canonical load_workspace command ID.
        REPL method: _load_model()
        Bus command: "load_workspace"
        Events: command.load_workspace.before / command.load_workspace.succeeded / command.load_workspace.failed
        """
        path = Path(arg.split()[0]).expanduser()

        if hasattr(self, 'gui_port') and self.gui_port:
            if not self.gui_port.confirm_discard_unsaved_changes():
                print("Load cancelled - unsaved changes")
                return
            success = self.gui_port.open_file(str(path))
            if success:
                print(f"Loaded model from {path}")
                self.workspace = self.gui_port.get_workspace()
            else:
                print(f"Failed to load model from {path}")
        else:
            if not path.exists():
                print(f"File not found: {path}")
                return
            try:
                result = self.session.execute("load_workspace", path=str(path))
                if result.success:
                    print(f"Loaded model from {path} (bus-driven)")
                else:
                    print(f"Error loading model: {result.error}")
            except Exception as e:
                print(f"Error loading model: {e}")

    def _load_data(self: OpenMREPLCore, arg: str):
        """Import data from file."""
        path = Path(arg.split()[0]).expanduser()

        if not path.exists():
            print(f"File not found: {path}")
            return

        ext = path.suffix.lower()
        try:
            if ext in ('.xlsx', '.xls'):
                try:
                    result = self.session.execute("run_excel_import", path=str(path))
                    if result.success:
                        data = result.data
                        print(f"Imported {data.get('values_loaded', 0)} values from {path.name}")
                        if data.get('warnings'):
                            print(f"Warnings: {'; '.join(data['warnings'])}")
                    else:
                        print(f"Import failed: {result.error}")
                except Exception as e:
                    print(f"Import failed: {e}")
            elif ext == '.csv':
                import pandas as pd
                df = pd.read_csv(path)
                print(f"Loaded CSV: {len(df)} rows, {len(df.columns)} columns")
                print(f"  Columns: {', '.join(df.columns[:5])}")
            else:
                print(f"Unsupported format: {ext}")
        except Exception as e:
            print(f"Error loading data: {e}")

    def do_save(self: OpenMREPLCore, arg: str):
        """
        Save data, macros, or models to file.
        Usage: save <filepath>            - Save workspace to file (auto-detect)
               save model <filepath>       - Save workspace/model
               save macro <name> [filepath] - Save macro by name to file

        Examples:
          save model_20260503.json
          save model ~/models/finance.openm
          save macro format_blue ~/format_blue.json
        """
        if not arg:
            print(self.do_save.__doc__)
            return

        parts = arg.split(maxsplit=1)

        if parts[0] in ("macro", "model"):
            if len(parts) < 2:
                print(f"Error: Usage: save {parts[0]} <filepath>")
                return
            save_type, rest = parts[0], parts[1]

            if save_type == "macro":
                self._save_macro(rest)
            elif save_type == "model":
                self._save_model(rest)
        else:
            self._save_model(arg)

    def _save_model(self: OpenMREPLCore, arg: str):
        """Save workspace/model to file.

        Phase 5: Uses canonical save_workspace command ID.
        REPL method: _save_model()
        Bus command: "save_workspace"
        Events: command.save_workspace.before / command.save_workspace.succeeded / command.save_workspace.failed
        """
        path = Path(arg.split()[0]).expanduser()

        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        try:
            result = self.session.execute("save_workspace", path=str(path))
            if result.success:
                print(f"Saved model to: {path}")
            else:
                print(f"Error saving model: {result.error}")
        except Exception as e:
            print(f"Error saving model: {e}")
            import traceback
            traceback.print_exc()

    def _save_macro(self: OpenMREPLCore, arg: str):
        """Save macro to file."""
        parts = arg.split()
        if not parts:
            print("Error: Usage: save macro <name> [filepath]")
            return

        macro_name = parts[0]
        custom_path = parts[1] if len(parts) > 1 else None

        from lib_utils.macro_recorder import get_recorder
        recorder = get_recorder()

        macro = recorder.load_macro(macro_name)
        if not macro:
            print(f"Macro '{macro_name}' not found")
            return

        try:
            if custom_path:
                path = Path(custom_path).expanduser()
            else:
                from lib_utils.paths import OM_EXPORTS_DIR
                path = OM_EXPORTS_DIR / f"{macro_name}.json"
                path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w") as f:
                import json
                json.dump(macro.to_dict(), f, indent=2)

            print(f"Saved macro '{macro_name}' to {path}")
        except Exception as e:
            print(f"Error saving macro: {e}")


    def do_source(self: OpenMREPLCore, arg: str):
        """
        Execute commands from a file (without saving to history).
        Usage: source <filename>
        Example: source test_scripts/01_basic_variables.openm
        
        Commands executed via source are NOT saved to command history.
        This allows you to load and run scripts without polluting your REPL history.
        """
        try:
            import readline
        except ImportError:
            readline = None
        
        if not arg:
            print("Error: No filename specified. Usage: source <filename>")
            return

        # Track source call stack so nested source paths resolve relative to the
        # script that contains them, and circular references are rejected.
        if not hasattr(self, "_source_stack"):
            self._source_stack: list[str] = []

        filepath = Path(arg).expanduser()
        if not filepath.is_absolute():
            if self._source_stack:
                base_dir = Path(self._source_stack[-1]).parent
            else:
                base_dir = Path.cwd()
            filepath = base_dir / filepath

        filepath = filepath.resolve()
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            return

        source_path = str(filepath)
        if source_path in self._source_stack:
            print(f"Error: Circular source detected: {filepath.name}")
            return

        # Disable history writes during source (same approach as macro playback)
        # In remote mode, skip_history is a local concern only; readline is not shared.
        _orig_add_history = None
        if readline is not None:
            _orig_add_history = readline.add_history
            readline.add_history = lambda *a, **kw: None  # no-op
        ctx = None
        try:
            ctx = self.session.context
            ctx.skip_history = True
        except (AttributeError, RuntimeError):
            pass  # Remote session or no context

        self._source_stack.append(source_path)
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()

            print(f"Sourcing {filepath} ({len(lines)} lines)...")
            executed = 0
            errors = []
            rule_batch: list[dict] = []

            def _flush_rule_batch() -> None:
                if not rule_batch:
                    return
                try:
                    result = self.session.execute("apply_rule_batch", rules=rule_batch)
                    if result.success:
                        print(f"Applied {len(rule_batch)} rule(s)")
                    else:
                        raise Exception(result.error or "Rule batch failed")
                except Exception as e:
                    errors.append((line_num, str(e), f"apply_rule_batch ({len(rule_batch)} rules)"))
                    raise
                finally:
                    rule_batch.clear()

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue

                try:
                    parts = stripped.split()
                    is_batchable_rule = (
                        parts
                        and parts[0].lower() == "rule"
                        and "=" in stripped
                        and (len(parts) == 1 or parts[1].lower() not in ("delete", "delete-anchored", "set-anchored"))
                    )
                    if is_batchable_rule:
                        rule_dict = self.do_rule(stripped[5:].strip(), batch_mode=True)
                        if rule_dict is not None:
                            rule_batch.append(rule_dict)
                            executed += 1
                            continue
                        # Parse failed; do_rule already reported it. Skip executing it again.
                        errors.append((line_num, "Invalid rule command", stripped))
                        continue
                    _flush_rule_batch()
                    self.onecmd(stripped)
                    executed += 1
                except Exception as e:
                    errors.append((line_num, str(e), stripped))

            try:
                _flush_rule_batch()
            except Exception:
                pass

            if errors:
                print(f"Executed {executed} commands, {len(errors)} errors:")
                for line_num, err, line in errors:
                    print(f"  Line {line_num}: {err}")
                    print(f"    {line[:60]}...")
            else:
                print(f"Executed {executed} commands from {filepath.name}")

        except Exception as e:
            print(f"Error reading file: {e}")
        finally:
            self._source_stack.pop()
            # Restore history writes
            try:
                if ctx is not None:
                    ctx.skip_history = False
            except (AttributeError, RuntimeError):
                pass
            if readline is not None and _orig_add_history is not None:
                readline.add_history = _orig_add_history

    def complete_source(self: OpenMREPLCore, text: str, line: str, begidx: int, endidx: int):
        """Tab completion for source command - file paths."""
        import glob
        from pathlib import Path

        typed = line[7:]  # len('source ') == 7

        if typed.startswith('~'):
            typed = str(Path.home()) + typed[1:]

        if '/' in typed:
            if typed.endswith('/'):
                dir_path = typed.rstrip('/')
                if not dir_path:
                    dir_path = '.'
                file_pattern = ''
            else:
                dir_path = str(Path(typed).parent) if typed else '.'
                file_pattern = str(Path(typed).name)
        else:
            dir_path = '.'
            file_pattern = typed

        try:
            results = []
            base_path = Path(dir_path)

            if not file_pattern:
                if base_path.exists():
                    for item in base_path.iterdir():
                        if item.is_dir() and not item.name.startswith('.'):
                            results.append(item.name + '/')

                for om_file in base_path.glob('*.openm'):
                    results.append(om_file.name)
            else:
                for match in base_path.glob(file_pattern + '*'):
                    if match.is_dir():
                        results.append(match.name + '/')
                    else:
                        results.append(match.name)

            results.sort(key=lambda x: (not x.endswith('/'), x.lower()))
            return results
        except Exception:
            return []