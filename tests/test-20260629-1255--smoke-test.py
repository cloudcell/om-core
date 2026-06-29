"""Smoke test runner for tests/scripts/test_20260629_1255_smoke_test.openm.

Executes the OpenM script line-by-line and verifies that the smoke test
script completes without assertion failures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib_command.core.executor import get_executor
from lib_openm.api import Engine
from lib_openm.model import demo_workspace
from lib_repl import OpenMREPL
from tests.helpers import _MockSession


class TestSmokeScript:
    """Run the smoke test .openm script and verify it passes."""

    def setup_method(self):
        self.repl = OpenMREPL(session=_MockSession(executor=get_executor()))
        self.workspace = demo_workspace()
        self.engine = Engine(self.workspace)
        self.repl.session.context.engine = self.engine
        self.repl.session.context.workspace = self.workspace

    def test_smoke_script_executes_successfully(self):
        """Execute the smoke test script and check for assertion failures."""
        script_path = Path("tests/scripts/test_20260629_1255_smoke_test.openm")
        assert script_path.exists(), f"Smoke test script not found: {script_path}"

        lines = [
            line.strip()
            for line in script_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        for line_num, line in enumerate(lines, 1):
            print(f"  Executing line {line_num}: {line}")
            result = self.repl.onecmd(line)
            if result is True:
                pytest.fail(f"Assertion failed in smoke test at line {line_num}: {line}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
