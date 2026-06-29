"""Pytest configuration and helpers for the OpenM engine tests.

This module ensures that the project root (which contains lib_openm, lib_gui,
etc.) is always on sys.path when tests are collected, so imports like
"lib_openm.api" work regardless of how pytest is invoked.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Add the project root to sys.path if it's missing.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

# Re-export canonical test helpers so they remain available via conftest auto-injection
from tests.helpers import make_test_envelope  # noqa: F401


# Global storage for test contexts (workspace, engine) to access in teardown
test_contexts: dict[str, Any] = {}


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "multithread: marks tests that use multithread recompute")
    config.addinivalue_line("markers", "no_multithread: marks tests that must NOT run in MT phase (Qt tests)")
    config.addinivalue_line("markers", "qt: marks tests that require Qt widget instantiation")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options for the OpenM test suite."""

    parser.addoption(
        "--save-openm-workspaces",
        action="store_true",
        default=False,
        help=(
            "Save workspaces created in tests under tests/run_<timestamp>/*.json "
            "for inspection in the GUI."
        ),
    )
    
    parser.addoption(
        "--save-failed-workbooks",
        metavar="DIR",
        default=None,
        help=(
            "Save workspace model files for failed tests to the specified directory. "
            "Each failed test gets a timestamped .json file for post-mortem analysis."
        ),
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Clear test context before each test."""
    test_contexts[item.nodeid] = None


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Capture test report and save failed workbooks.
    
    This hook runs after each test phase (setup, call, teardown) and captures
    the test outcome. If the test failed and --save-failed-workbooks is enabled,
    the workspace is saved to the specified directory.
    """
    outcome = yield
    report = outcome.get_result()
    
    # Only save on the 'call' phase (actual test execution) when test failed
    if call.when != "call":
        return
    
    if report.outcome != "failed":
        return
    
    # Check if --save-failed-workbooks is enabled
    failed_workbooks_dir = item.config.getoption("--save-failed-workbooks")
    if not failed_workbooks_dir:
        return
    
    # Get the test context (engine)
    context = test_contexts.get(item.nodeid)
    if context is None:
        return
    
    engine = context.get("engine")
    if engine is None or not hasattr(engine, "_ws"):
        return
    
    ws = engine._ws
    if ws is None:
        return
    
    # Create output directory
    output_dir = Path(failed_workbooks_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename: <test_name>_<timestamp>.json
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_test_name = item.name.replace("[", "_").replace("]", "_").replace("/", "_")
    filename = f"{safe_test_name}_{timestamp}.json"
    filepath = output_dir / filename
    
    try:
        # Save workspace to JSON using the persistence module
        from lib_openm.persistence import save_workspace
        save_workspace(str(filepath), ws)
        print(f"\n[FAILED TEST WORKBOOK SAVED] {filepath}")
    except Exception as e:
        print(f"\n[FAILED TO SAVE WORKBOOK] {filepath}: {e}")


@pytest.fixture(scope="session")
def save_openm_workspaces(request: pytest.FixtureRequest) -> bool:
    """Return True if --save-openm-workspaces was passed on the pytest CLI."""

    return bool(request.config.getoption("--save-openm-workspaces"))


@pytest.fixture
def register_test_engine(request: pytest.FixtureRequest):
    """Fixture to register an engine for saving if the test fails.
    
    Usage in tests:
        def test_something(register_test_engine):
            ws = Workspace.create("Test")
            engine = Engine(ws)
            register_test_engine(engine)  # Register for failure saving
            # ... rest of test
    """
    def _register(engine):
        test_contexts[request.node.nodeid] = {"engine": engine}
    return _register


@pytest.fixture(autouse=True)
def capture_engines_for_failure_saving(request: pytest.FixtureRequest):
    """Automatically capture Engine instances for saving on test failure.
    
    This patches Engine.__init__ to register each created engine with the
    current test context, enabling automatic workbook saving when tests fail
    and --save-failed-workbooks is enabled.
    """
    from lib_openm.api import Engine
    
    # Skip if not saving failed workbooks
    if not request.config.getoption("--save-failed-workbooks"):
        yield
        return
    
    original_init = Engine.__init__
    
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Register this engine with the current test
        test_contexts[request.node.nodeid] = {"engine": self}
    
    Engine.__init__ = patched_init
    yield
    Engine.__init__ = original_init


@pytest.fixture(autouse=True)
def disable_multithread_recompute_by_default(request: pytest.FixtureRequest) -> None:
    """Disable multithread recompute to avoid Qt/ThreadPoolExecutor deadlocks.
    
    For non-MT tests: MT is disabled and parallel recompute is patched to return 0
    (forcing serial fallback). This prevents hangs when Qt tests run before MT tests.
    
    For MT-marked tests: The fixture does nothing, allowing full MT functionality.
    MT tests should be run FIRST in isolation (before Qt initializes).
    """
    from lib_openm.api import Engine
    
    # If this is an MT-marked test, don't patch anything - allow full MT functionality
    if request.node.get_closest_marker("multithread"):
        yield
        return
    
    # For non-MT tests: patch to disable MT and force serial fallback
    original_init = Engine.__init__
    original_parallel = Engine._recompute_dirty_nodes_parallel
    original_enable_mt = Engine.enable_multithread_recompute
    
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._multithread_recompute_enabled = False
    
    def patched_parallel(self, *, max_nodes=None):
        # Force serial fallback by returning 0 (no parallel processing)
        return 0
    
    def patched_enable_mt(self, enabled=True, *, max_workers=None):
        # No-op: keep MT disabled to avoid ThreadPoolExecutor/Qt deadlock
        self._multithread_recompute_enabled = False
        if max_workers is not None:
            self._multithread_recompute_workers = max(1, int(max_workers))
    
    Engine.__init__ = patched_init
    Engine._recompute_dirty_nodes_parallel = patched_parallel
    Engine.enable_multithread_recompute = patched_enable_mt
    yield
    Engine.__init__ = original_init
    Engine._recompute_dirty_nodes_parallel = original_parallel
    Engine.enable_multithread_recompute = original_enable_mt


@pytest.fixture(autouse=True)
def suppress_gui_debug_output():
    """Suppress DEBUG print statements from GUI code during tests."""
    import sys
    from io import StringIO
    
    # Store original stdout/stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Create filtered stdout that drops DEBUG lines
    class DebugFilter:
        def __init__(self, target):
            self.target = target
            
        def write(self, text):
            # Drop lines containing DEBUG or specific GUI/engine debug patterns
            if text.strip() and not any(x in text for x in [
                "DEBUG ",
                "active_table:",
                "focus_changed:",
                "_sync_rule_bar:",
                "_on_table_selection_changed:",
                "_on_local_sel_changed:",
                "_current_focus_desc:",
                "focus_desc:",
                "SET CELL:",
                "COLUMNS:",
                "ROWS:",
                "GRID LAYOUT",
                "ROW MODE:",
                "COL MODE:",
                "This plugin does not support",
                "propagateSizeHints",
                "[timing]",
                "[ENGINE]",
                "[GUI]",
                "[TEST]",
                "[Test]",
                "Esc shortcut created",
                "===",  # All === separator lines
                "---",  # All --- separator lines (like ----...)
                "labels=[",
                "paths=[",
                "ROW BANDS:",
                "COLUMN BANDS:",
                "level=",
                "shaded=",
                "Mouse event",  # Covers all mouse event variations
                "mouse event",  # Case variations
                "not accepted by receiving widget",
                "EDIT MODE:",
                "bar=<PySide6",
                "multi-cell fill:",
                "Fuzz test completed",
                "Edge case fuzz test completed",
                "Workspace:",
                " cubes, ",
                "inner=",
                "error=",
                "... (",  # "... (30 more rows)"
                "Multi-item reorder test passed",
            ]):
                self.target.write(text)
                
        def flush(self):
            self.target.flush()
            
        def isatty(self):
            return False
    
    # Apply filter
    sys.stdout = DebugFilter(original_stdout)
    sys.stderr = DebugFilter(original_stderr)
    
    yield
    
    # Restore
    sys.stdout = original_stdout
    sys.stderr = original_stderr
