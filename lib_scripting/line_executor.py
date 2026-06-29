"""ScriptLineExecutor — shared script-line semantics for REPL, TUI, and macro playback.

Owns:
- Quote-aware interpolation (`{{name}}`)
- Variable assignment detection and `set_variable` emission
- `exec {{cmd}}` execution with safety rules
- Command parsing and `do_*` dispatch

Does NOT own:
- `cmd.Cmd` lifecycle (`precmd`, `postcmd`)
- History management
- Terminal/echo handling
"""

from __future__ import annotations

import io
import re
import warnings
from contextlib import redirect_stdout
from typing import Any


class ScriptLineExecutor:
    """Execute a single script line with interpolation and dispatch.

    The caller (REPL, TUI, or MacroPlaybackRunner) provides the instance
    that owns `session`, `variables`, `global_vars`, and `do_*` methods.
    """

    def __init__(self, instance: Any) -> None:
        self.instance = instance

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_line(self, line: str) -> Any:
        """Execute one line: interpolate, parse, dispatch.

        Returns the result from the dispatched `do_*` method, or None.
        """
        line = line.strip()
        if not line:
            return None

        # 1. Variable assignment
        result = self._try_variable_assignment(line)
        if result is not None:
            return result

        # 2. Quote-aware interpolation
        line = self._interpolate(line)

        # 3. exec {{cmd}} handling
        if line.startswith("exec"):
            return self._handle_exec(line)

        # 4. Legacy $var / $(cmd) expansion (deprecated)
        line = self._try_legacy_dollar_expansion(line)

        # 5. Parse and dispatch
        return self._dispatch(line)

    # ------------------------------------------------------------------
    # Variable assignment
    # ------------------------------------------------------------------

    def _exec_and_capture(self, cmd_line: str) -> str:
        """Execute a command line and capture its return value as a string."""
        cmd, arg, _ = self.instance.parseline(cmd_line)
        if not cmd:
            return ""
        func = getattr(self.instance, f"do_{cmd}", None)
        if func:
            result = func(arg)
            if result is None:
                return ""
            if isinstance(result, list):
                return " ".join(str(x) for x in result)
            return str(result)
        # Try default() for registered command IDs
        default = getattr(self.instance, "default", None)
        if default:
            result = default(cmd_line)
            if result is not None:
                return str(result)
        return ""

    def _try_variable_assignment(self, line: str) -> Any | None:
        """Detect var/set/= assignment and emit set_variable through session."""
        # Explicit var / set keyword: var name = value (with optional -g)
        var_match = re.match(
            r'^(?:var|set)\s+(-g\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$',
            line,
        )
        if var_match:
            is_global = var_match.group(1) is not None
            var_name = var_match.group(2)
            value = var_match.group(3).strip()
            # Canonical: var ts = exec timestamp %Y%m%d_%H%M%S
            if value.startswith("exec "):
                cmd_line = value[5:].strip()
                cmd_line = self._interpolate(cmd_line)
                parsed = self._exec_and_capture(cmd_line)
            else:
                # Legacy: expand $(cmd) and $var in assignment values
                value = self._expand_legacy_commands(value)
                value = self._expand_legacy_variables(value)
                parsed = self._parse_value(value)
            return self._emit_set_variable(var_name, parsed, bool(is_global))

        # Bash-style assignment: name=value (no spaces around =)
        # But NOT if it looks like a cube::address rule
        if '::' not in line:
            assign_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$', line)
            if assign_match:
                var_name = assign_match.group(1)
                value = assign_match.group(2).strip()
                # Canonical: ts=exec timestamp %Y%m%d_%H%M%S
                if value.startswith("exec "):
                    cmd_line = value[5:].strip()
                    cmd_line = self._interpolate(cmd_line)
                    parsed = self._exec_and_capture(cmd_line)
                else:
                    # Legacy: expand $(cmd) and $var in assignment values
                    value = self._expand_legacy_commands(value)
                    value = self._expand_legacy_variables(value)
                    parsed = self._parse_value(value)
                return self._emit_set_variable(var_name, parsed, False)

        return None

    def _emit_set_variable(self, name: str, value: Any, global_scope: bool) -> Any:
        """Emit set_variable through session.execute if available."""
        session = getattr(self.instance, "session", None)
        if session is not None:
            result = session.execute(
                "set_variable",
                name=name,
                value=value,
                global_scope=global_scope,
            )
            if result and getattr(result, "success", False):
                self._print_variable_set(name, value, global_scope)
                return False

        # Fallback: direct mutation
        if global_scope:
            self.instance.global_vars[name] = value
        else:
            self.instance.variables[name] = value
        self._print_variable_set(name, value, global_scope)
        return False

    def _print_variable_set(self, name: str, value: Any, global_scope: bool) -> None:
        scope = "Global variable" if global_scope else "Variable"
        if isinstance(value, list):
            print(f"{scope} '{name}' set ({len(value)} items)")
        else:
            print(f"{scope} '{name}' = {value!r}")

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------

    def _parse_value(self, value: str) -> Any:
        """Parse a string value into appropriate type."""
        value = value.strip()
        # Check for quoted string
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        # Check for space-separated list
        if ' ' in value and not value.startswith('('):
            parts = value.split()
            return [self._parse_value(part) for part in parts]
        # Single value parsing
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                if value.lower() in ('true', 'yes'):
                    return True
                elif value.lower() in ('false', 'no'):
                    return False
                return value

    # ------------------------------------------------------------------
    # Quote-aware interpolation
    # ------------------------------------------------------------------

    def _interpolate(self, line: str) -> str:
        """Expand {{name}} placeholders everywhere, including inside quotes."""
        result_parts = []
        i = 0
        while i < len(line):
            if line[i:i + 2] == "{{":
                end = line.find("}}", i + 2)
                if end == -1:
                    result_parts.append(line[i])
                    i += 1
                else:
                    var_name = line[i + 2:end].strip()
                    replacement = self._resolve_name(var_name)
                    result_parts.append(replacement)
                    i = end + 2
            else:
                result_parts.append(line[i])
                i += 1
        return "".join(result_parts)

    def _resolve_name(self, name: str) -> str:
        """Resolve {{name}}: check variables, then try do_name() method."""
        variables = self.instance.variables
        if name in variables:
            value = variables[name]
            if isinstance(value, list):
                return " ".join(str(v) for v in value)
            return str(value)

        # Try REPL command substitution: {{views}} calls do_views()
        cmd_method = f"do_{name}"
        if hasattr(self.instance, cmd_method):
            f = io.StringIO()
            try:
                with redirect_stdout(f):
                    result = getattr(self.instance, cmd_method)("")
            except Exception:
                return f"{{{{{name}}}}}"
            output = f.getvalue().strip()
            if result is not None and result != "":
                return str(result)
            if output:
                return output

        return f"{{{{{name}}}}}"

    # ------------------------------------------------------------------
    # exec safety rules
    # ------------------------------------------------------------------

    def _handle_exec(self, line: str) -> Any:
        """Execute an expanded command string. Safety: single-line, no recursion."""
        # Strip "exec " prefix
        payload = line[5:].strip()
        if not payload:
            print("Error: exec requires a command argument")
            return False

        # Reject multi-command payloads
        separators = ['\n', ';', '&&', '||']
        for sep in separators:
            if sep in payload:
                print(f"Error: exec rejects multi-command payload (found '{sep}')")
                return False

        # Reject nested exec
        if payload.startswith("exec "):
            print("Error: exec does not support nested exec")
            return False

        # Reject empty/whitespace-only
        if not payload.strip():
            print("Error: exec requires a non-empty command")
            return False

        return self._dispatch(payload)

    # ------------------------------------------------------------------
    # Legacy $ expansion (deprecated)
    # ------------------------------------------------------------------

    def _try_legacy_dollar_expansion(self, line: str) -> str:
        """Expand legacy $var and $(cmd) with deprecation warning."""
        if '$' not in line:
            return line

        # Check for $var or ${var}
        if re.search(r'\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*', line):
            warnings.warn(
                "Legacy $var and $(cmd) syntax is deprecated. Use {{name}} and exec {{cmd}}.",
                DeprecationWarning,
                stacklevel=3,
            )
            line = self._expand_legacy_variables(line)

        # Check for $(cmd)
        if re.search(r'\$\([^)]+\)', line):
            warnings.warn(
                "Legacy $(cmd) syntax is deprecated. Use exec {{cmd}}.",
                DeprecationWarning,
                stacklevel=3,
            )
            line = self._expand_legacy_commands(line)

        return line

    def _expand_legacy_variables(self, line: str) -> str:
        """Expand $var and ${var} to their stored values."""
        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            variables = self.instance.variables
            if var_name in variables:
                value = variables[var_name]
                if isinstance(value, list):
                    return ",".join(str(v) for v in value)
                return str(value)
            return match.group(0)
        return re.sub(r'\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)', replace_var, line)

    def _expand_legacy_commands(self, line: str) -> str:
        """Replace $(command) with the command's return value."""
        def execute_and_capture(match):
            inner_cmd = match.group(1).strip()
            cmd_name, arg, _ = self.instance.parseline(inner_cmd)
            if cmd_name and hasattr(self.instance, f'do_{cmd_name}'):
                method = getattr(self.instance, f'do_{cmd_name}')
                result = method(arg)
                if result is None:
                    return ""
                elif isinstance(result, list):
                    return " ".join(str(x) for x in result)
                else:
                    return str(result)
            return ""
        # Process substitutions repeatedly (for nested cases)
        max_iterations = 10
        for _ in range(max_iterations):
            new_line = re.sub(r'\$\(([^)]+)\)', execute_and_capture, line)
            if new_line == line:
                break
            line = new_line
        return line

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, line: str) -> Any:
        """Parse line and dispatch to do_* method, or default() for registered commands."""
        cmd, arg, _ = self.instance.parseline(line)
        if not cmd:
            return None

        # Case-insensitive dispatch
        cmd = cmd.lower()

        # Exit commands
        if cmd in ('quit', 'exit', 'EOF'):
            return self._dispatch_exit(cmd, arg)

        func = getattr(self.instance, f"do_{cmd}", None)
        if func:
            return func(arg)

        # Fall through to default() for registered command IDs (e.g. set_cell)
        default = getattr(self.instance, "default", None)
        if default:
            return default(line)

        print(f"Unknown command: {cmd}")
        print("Type 'help' for available commands")
        return False

    def _dispatch_exit(self, cmd: str, arg: str) -> Any:
        """Handle exit commands. Delegates to instance's exit handler if present."""
        func = getattr(self.instance, f"do_{cmd}", None)
        if func:
            return func(arg)
        return True
