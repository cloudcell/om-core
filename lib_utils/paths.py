"""Centralized home directory paths for OM.

All user-facing file system paths live here so they can be changed
in one place.  Modules must import from this module instead of
hard-coding ``Path.home() / ".om" / …`` directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Toggle local development mode. When True and running from source, OM_HOME
# defaults to a ./.om/ directory inside the project root instead of the user's
# home directory. PyInstaller/standalone builds always use the directory
# containing the executable as the portable root. Set OM_HOME env var to
# override any of these defaults.
LOCALDEV = True  # False


def _default_om_home() -> Path:
    if getattr(sys, "frozen", False):
        # Portable one-directory build: .om/ should live next to the executable.
        # We also check a few related candidates because some Windows PyInstaller
        # layouts or launchers can put the executable one level deeper than the
        # bundle root.
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [exe_dir, exe_dir.parent]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_dir = Path(meipass).resolve()
            candidates.append(meipass_dir.parent)
            candidates.append(meipass_dir)
        for candidate in candidates:
            if (candidate / ".om").exists():
                return candidate / ".om"
        return exe_dir / ".om"
    if LOCALDEV:
        # Source development: project root is two levels up from this file.
        return Path(__file__).resolve().parent.parent / ".om"
    return Path.home() / ".om"


# Base directory (override via OM_HOME env var for testing / portable installs)
OM_HOME = Path(os.environ.get("OM_HOME", _default_om_home()))

# Sub-directories
OM_CONFIG_DIR = OM_HOME / "config"
OM_TOOLBARS_DIR = OM_HOME / "toolbars"
OM_MACROS_DIR = OM_HOME / "macros"
OM_EXPORTS_DIR = OM_HOME / "exports"
OM_RECORDINGS_DIR = OM_HOME / "recordings"
OM_SESSIONS_DIR = OM_HOME / "sessions"
OM_UDF_DIR = OM_HOME / "udf"

# Specific files
OM_HISTORY_FILE = Path.home() / ".om_history"
DEFAULT_TOOLBOX_CONFIG_PATH = OM_CONFIG_DIR / "gui-toolbox.conf"
WIDGET_PALETTE_CUSTOM_PATH = OM_CONFIG_DIR / "widget-palette-custom.conf"
