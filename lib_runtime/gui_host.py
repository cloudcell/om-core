"""lib_runtime.gui_host — GUI application entry point.

Creates QApplication, wires runtime, then constructs MainWindow with
a prebuilt client session. This is the canonical GUI entry point.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from lib_runtime.app_host import create_runtime_context


def _set_macos_app_menu_title(title: str) -> None:
    """Force the macOS application menu title in the menu bar.

    When running from a Python script (not a .app bundle), macOS shows the
    Python process name as the application menu title. Qt's
    setApplicationDisplayName does not override that title. We set the title
    of NSApp.mainMenu's first item directly via the Objective-C runtime.
    """
    if sys.platform != "darwin":
        return

    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("AppKit"))

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]

        def _sel(name: str) -> ctypes.c_void_p:
            return objc.sel_registerName(name.encode())

        def _send(ret_type, *arg_types):
            return ctypes.CFUNCTYPE(ret_type, *arg_types)(objc.objc_msgSend.address)

        send_pp = _send(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        ns_app = send_pp(objc.objc_getClass(b"NSApplication"), _sel("sharedApplication"))

        main_menu = send_pp(ns_app, _sel("mainMenu"))
        first_item = _send(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)(
            main_menu, _sel("itemAtIndex:"), 0
        )
        title_str = _send(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(
            objc.objc_getClass(b"NSString"), _sel("stringWithUTF8String:"), title.encode()
        )
        _send(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            first_item, _sel("setTitle:"), title_str
        )
    except Exception:
        # If the Objective-C runtime dance fails, the app still starts; the
        # menu bar just keeps the Python process name.
        pass


def run_with_splash(
    app: QtWidgets.QApplication,
    splash: Any,
    load_path: str | None = None,
) -> None:
    """Run the application with an externally provided splash screen.

    Creates the runtime session in lib_runtime, then passes the prebuilt
    client session to MainWindow. Engine construction lives outside lib_gui.

    Args:
        load_path: Optional workspace file to load before opening the window.
    """
    app.setApplicationName("OM Core")
    if sys.platform == "darwin":
        app.setApplicationDisplayName("OM Core")
    _setup_app_palette_and_styles(app)

    def update_progress(value: int, message: str) -> None:
        splash.set_progress(value, message)

    # Runtime composition happens in lib_runtime, not lib_gui
    runtime = create_runtime_context()

    if load_path:
        try:
            update_progress(25, f"Loading {Path(load_path).name}...")
            runtime.command_session.execute("load_workspace", path=load_path)
        except Exception as exc:
            import warnings
            warnings.warn(f"Failed to load workspace {load_path}: {exc}", RuntimeWarning)

    from lib_gui.app import MainWindow
    from lib_plugins.loader import load_plugins
    from lib_command.support.macro_recorder import get_recorder
    from lib_runner.macro_runner import MacroPlaybackRunner
    from lib_runtime.repl_host import _create_script_parser_module

    recorder = get_recorder()
    macro_runner = MacroPlaybackRunner(
        session=runtime.command_session,
        script_parser_module=_create_script_parser_module(),
    )

    win = MainWindow(
        progress_callback=update_progress,
        defer_window_restore=True,
        session=runtime.command_session,
        recorder=recorder,
        macro_runner=macro_runner,
    )

    # Wire the GUI profiler into the session context so in-process query
    # handlers (e.g. grid_viewport_snapshot) can contribute spans to the
    # GUI profiler report.
    try:
        ctx = runtime.command_session.context
        if ctx is not None:
            ctx.profiler = win.profiler
    except Exception:
        pass

    # Load plugins after menus are created inside MainWindow.__init__
    loaded, errors = load_plugins(win, win._plugins_menu)
    if not loaded and win._plugins_menu.isEmpty():
        win._plugins_menu.setEnabled(False)
    if errors:
        import warnings
        warnings.warn("Plugin load errors: " + "; ".join(errors), RuntimeWarning)

    def on_about_to_quit():
        win._save_window_state()
        if getattr(win, '_recalculating', False) and win._recalc_thread is not None and win._recalc_thread.isRunning():
            print("[GUI] Application quitting during calculation - force terminating")
            os.kill(os.getpid(), signal.SIGKILL)
        try:
            runtime.engine.shutdown_engine()
        except Exception:
            pass

    app.aboutToQuit.connect(on_about_to_quit)

    win._tabs.setStyleSheet(
        """
QTabBar::tab {
    border: 1px solid transparent;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #d8dce4;
    color: #1f1f1f;
    border-color: #d8dce4;
}

QTabBar::tab:!selected {
    background-color: #f4f5f7;
    color: #202020;
    border-color: #d8dce4;
}
        """
    )

    splash.close()
    app.processEvents()
    win.show()
    win.restore_window_state_now()
    _set_macos_app_menu_title("OM Core")
    app.exec()


def run_gui_in_thread() -> tuple[threading.Thread, Any, QtWidgets.QApplication, threading.Event]:
    """Run GUI in a background thread, returning control to caller immediately.

    Creates the runtime session in lib_runtime before constructing MainWindow.
    """
    result_container: dict = {}
    exit_event = threading.Event()

    def qt_thread_target():
        # macOS uses the application name for the menu bar and About menu.
        # Configure it statically before creating QApplication and pass OM Core as
        # argv[0] so the native menu bar shows "OM Core" instead of "python".
        QtCore.QCoreApplication.setApplicationName("OM Core")
        if sys.platform == "darwin":
            QtGui.QGuiApplication.setApplicationDisplayName("OM Core")
        app = QtWidgets.QApplication(["OM Core"])
        app.setApplicationName("OM Core")
        if sys.platform == "darwin":
            app.setApplicationDisplayName("OM Core")
        app.setStyle("Fusion")

        _setup_app_palette_and_styles(app)

        splash = _create_splash_in_thread(app)
        if splash is not None:
            splash.show()
            app.processEvents()

        def update_progress(value: int, message: str) -> None:
            if splash is not None:
                splash.set_progress(value, message)

        runtime = create_runtime_context()

        from lib_gui.app import MainWindow
        from lib_plugins.loader import load_plugins
        from lib_command.support.macro_recorder import get_recorder
        from lib_runner.macro_runner import MacroPlaybackRunner
        from lib_runtime.repl_host import _create_script_parser_module

        recorder = get_recorder()
        macro_runner = MacroPlaybackRunner(
            session=runtime.command_session,
            script_parser_module=_create_script_parser_module(),
        )

        win = MainWindow(
            progress_callback=update_progress,
            defer_window_restore=True,
            session=runtime.command_session,
            recorder=recorder,
            macro_runner=macro_runner,
        )

        # Wire the GUI profiler into the session context so in-process query
        # handlers (e.g. grid_viewport_snapshot) can contribute spans.
        try:
            ctx = runtime.command_session.context
            if ctx is not None:
                ctx.profiler = win.profiler
        except Exception:
            pass

        # Load plugins after menus are created inside MainWindow.__init__
        loaded, errors = load_plugins(win, win._plugins_menu)
        if not loaded and win._plugins_menu.isEmpty():
            win._plugins_menu.setEnabled(False)
        if errors:
            import warnings
            warnings.warn("Plugin load errors: " + "; ".join(errors), RuntimeWarning)

        def on_about_to_quit():
            win._save_window_state()
            try:
                runtime.engine.shutdown_engine()
            except Exception:
                pass

        app.aboutToQuit.connect(on_about_to_quit)

        def on_last_window_closed():
            exit_event.set()
            app.quit()

        app.lastWindowClosed.connect(on_last_window_closed)

        if splash is not None:
            splash.close()
            app.processEvents()
        win.show()
        win.restore_window_state_now()
        _set_macos_app_menu_title("OM Core")

        result_container['app'] = app
        result_container['window'] = win
        result_container['exit_event'] = exit_event
        result_container['thread_id'] = threading.current_thread().ident

        app.exec()

        win.deleteLater()
        app.processEvents()
        app.sendPostedEvents()
        time.sleep(0.05)

    qt_thread = threading.Thread(target=qt_thread_target, daemon=False)
    qt_thread.start()

    timeout = 30.0
    start = time.monotonic()
    while 'window' not in result_container and (time.monotonic() - start) < timeout:
        time.sleep(0.1)

    if 'window' not in result_container:
        raise RuntimeError("GUI failed to start within timeout")

    return qt_thread, result_container['window'], result_container['app'], result_container['exit_event']


def _create_splash_in_thread(app: QtWidgets.QApplication) -> Any:
    """Create a splash screen inside the Qt thread."""
    from lib_gui.splash import SplashScreen
    try:
        return SplashScreen(app)
    except Exception:
        return None


def start_gui(endpoint: Any | None = None) -> None:
    """Start GUI as a pure client connecting to an existing runtime.

    Creates QApplication, connects to transport, creates RemoteCommandSession,
    then constructs MainWindow.

    Note: MainWindow currently accesses session.context, session.gateway.bus,
    and other local-only attributes. Full remote GUI support requires
    refactoring MainWindow to use session.query() instead of direct context
    access. During transition, --gui-only may be used for in-process mode.
    """
    import logging
    from lib_command.core.transport_socket_client import SocketTransportClient
    from lib_command.core.remote_session import RemoteCommandSession
    from lib_command.core.transport_base import TransportEndpoint

    logger = logging.getLogger(__name__)

    if endpoint is None:
        endpoint = _resolve_client_endpoint()

    # macOS app name handling
    QtCore.QCoreApplication.setApplicationName("OM Core")
    if sys.platform == "darwin":
        QtGui.QGuiApplication.setApplicationDisplayName("OM Core")
    argv = ["OM Core"] + sys.argv[1:]
    app = QtWidgets.QApplication(argv)
    app.setApplicationName("OM Core")
    if sys.platform == "darwin":
        app.setApplicationDisplayName("OM Core")
    _setup_app_palette_and_styles(app)

    # Create and show splash screen
    from lib_gui.splash import SplashScreen
    splash: Any = None
    try:
        splash = SplashScreen(app)
        cursor_pos = QtGui.QCursor.pos()
        screen = QtWidgets.QApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        geom = screen.availableGeometry()
        splash.move(geom.x() + (geom.width() - 480) // 2, geom.y() + (geom.height() - 320) // 2)
        splash.show()
        app.processEvents()
    except Exception as exc:
        print(f"[GUI] Splash screen creation failed: {exc}", file=sys.stderr)

    if splash is not None:
        splash.set_progress(10, 'Connecting to runtime...')

    from lib_gui import config as _gui_config
    client = SocketTransportClient(
        endpoint,
        timeout=_gui_config.TRANSPORT_TIMEOUT_SECONDS,
    )
    try:
        if splash is not None:
            splash.set_progress(40, 'Opening session...')
            app.processEvents()
        client.connect()
        session_id = client.open_session(client_type="gui")
        logger.info("GUI session opened: %s", session_id)

        if splash is not None:
            splash.set_progress(70, 'Loading workspace...')
            app.processEvents()

        session = RemoteCommandSession(
            client, session_id,
            heartbeat_interval=_gui_config.HEARTBEAT_INTERVAL_SECONDS,
        )
        print(f"GUI connected to runtime at {endpoint}")

        from lib_command.support.macro_recorder import get_recorder
        from lib_runner.macro_runner import MacroPlaybackRunner

        recorder = get_recorder()
        macro_runner = MacroPlaybackRunner(session=session)

        # TODO: MainWindow needs refactoring to work with RemoteCommandSession
        # (remove session.context, session.gateway.bus access; use queries).
        # For now, this path may fail if MainWindow accesses local-only attrs.
        from lib_gui.app import MainWindow
        win = MainWindow(
            session=session,
            defer_window_restore=True,
            recorder=recorder,
            macro_runner=macro_runner,
        )

        if splash is not None:
            splash.set_progress(100, 'Ready')
            splash.close()
            app.processEvents()

        win.show()
        win.restore_window_state_now()
        _set_macos_app_menu_title("OM Core")

        def on_about_to_quit():
            win._save_window_state()
            # Stop transport threads before Qt teardown to avoid
            # "QThread: Destroyed while thread is still running" crashes.
            try:
                session.close()
            except Exception:
                pass

        app.aboutToQuit.connect(on_about_to_quit)
        app.exec()
    except Exception as exc:
        print(f"Error: Cannot connect to OM runtime at {endpoint}.")
        print("Start the runtime first with: python main.py --runtime")
        print(f"  Detail: {exc}")
        sys.exit(1)
    finally:
        client.close()


def _resolve_client_endpoint() -> Any:
    """Resolve transport endpoint for the GUI client."""
    import os
    from lib_command.core.transport_base import TransportEndpoint

    args = sys.argv

    if '--socket' in args:
        idx = args.index('--socket')
        if idx + 1 < len(args):
            return TransportEndpoint(kind="unix", path=args[idx + 1])

    host = None
    port = None
    if '--host' in args:
        idx = args.index('--host')
        if idx + 1 < len(args):
            host = args[idx + 1]
    if '--port' in args:
        idx = args.index('--port')
        if idx + 1 < len(args):
            try:
                port = int(args[idx + 1])
            except ValueError:
                port = None

    if host is not None or port is not None:
        return TransportEndpoint(kind="tcp", host=host or "127.0.0.1", port=port or 17391)

    socket_path = os.environ.get("OPENM_TRANSPORT_SOCKET")
    if socket_path:
        return TransportEndpoint(kind="unix", path=socket_path)

    env_host = os.environ.get("OPENM_TRANSPORT_HOST")
    env_port = os.environ.get("OPENM_TRANSPORT_PORT")
    if env_host is not None or env_port is not None:
        try:
            p = int(env_port) if env_port else 17391
        except ValueError:
            p = 17391
        return TransportEndpoint(kind="tcp", host=env_host or "127.0.0.1", port=p)

    if os.name == "nt":
        return TransportEndpoint(kind="tcp", host="127.0.0.1", port=17391)
    else:
        return TransportEndpoint(
            kind="unix",
            path=f"/tmp/openm-{os.environ.get('USER', 'unknown')}.sock",
        )


def _setup_app_palette_and_styles(app: QtWidgets.QApplication) -> None:
    """Set up application palette and stylesheet."""
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(245, 246, 247))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(255, 255, 255))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(248, 248, 248))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(245, 246, 247))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(20, 20, 20))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(20, 20, 20))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(46, 134, 193))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet(
        "QDockWidget::title { padding: 6px; font-weight: 600; }"
        "QTabBar::tab { padding: 6px 10px; }"
        "QLineEdit { padding: 4px; }"
        "QToolBar { spacing: 6px; }"
        "QMenu::item:selected { background-color: #d0d7e2; color: #000000; }"
        "QMenu::item:checked { background-color: #c0c7d2; color: #000000; }"
        "QComboBox QAbstractItemView::item:selected { background-color: #d0d7e2; color: #000000; }"
    )
