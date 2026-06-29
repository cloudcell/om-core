#!/usr/bin/env python3
"""Build a standalone Linux release tarball for OpenModeling.

Usage:
    source ./venv/bin/activate
    python scripts/build_release.py
    python scripts/build_release.py --cython
    python scripts/build_release.py --protected
    python scripts/build_release.py --cython --protected

Produces:
    out/OpenModeling-<version>-linux-x86_64-<timestamp>.tar.gz

The release is a one-directory PyInstaller bundle with the executable named
`OpenModeling`, bundled demo workspaces, default configs, and a README.

Options:
    --cython     Compile selected engine modules to Cython C extensions.
    --protected  Enable PyInstaller protection/optimization flags:
                 optimize=2, strip=True, upx=False, and disable windowed
                 traceback output.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Allow the build script to import project modules such as lib_utils.config.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from lib_utils.config import get_config
import build_common


VERSION = build_common.project_version(_PROJECT_ROOT)
APP_NAME = "OpenModeling"


def _build_timestamp() -> str:
    """Return the current local build timestamp as YYYYMMDD-HHMMSS."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _venv_python(project_root: Path) -> Path:
    return project_root / "venv" / "bin" / "python"


def _latest_demos(project_root: Path) -> list[Path]:
    """Return the newest demo file for each DEMO-NN category."""
    groups: dict[str, list[Path]] = {}
    for path in sorted(project_root.glob("DEMO-*.json")):
        name = path.stem
        if not name.startswith("DEMO-"):
            continue
        # DEMO-01--..., DEMO-02--..., etc.
        prefix = name.split("--")[0] if "--" in name else name
        groups.setdefault(prefix, []).append(path)
    demos: list[Path] = []
    for prefix in sorted(groups):
        # Choose the newest by filename (timestamp suffix).
        demos.append(sorted(groups[prefix])[-1])
    return demos


def _build_pyinstaller(
    project_root: Path,
    use_cython: bool = False,
    protected: bool = False,
) -> Path:
    python = _venv_python(project_root)
    if not python.exists():
        raise RuntimeError(f"Virtual environment Python not found: {python}")

    dist_dir = project_root / "dist" / APP_NAME
    # Clean previous build so the tarball is deterministic.
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    # Build the data file and hidden-import lists for the spec.
    datas: list[tuple[str, str]] = [
        (str(project_root / "assets" / "icons"), "assets/icons"),
        (str(project_root / "assets" / "logo"), "assets/logo"),
        (str(project_root / "version-manual.txt"), "."),
        (str(project_root / "version.txt"), "."),
    ]
    for demo in _latest_demos(project_root):
        datas.append((str(demo), "demos"))

    hiddenimports = [
        "lib_plugins.excel.plugin",
        "lib_repl",
        "lib_tui",
        "lib_runtime.runtime_host",
        "lib_runtime.cli_host",
        "lib_runtime.repl_host",
        "lib_runtime.tui_host",
    ]

    # Protection/optimization toggles.
    optimize = 2 if protected else 0
    strip = protected
    upx = not protected
    disable_windowed_traceback = protected

    spec_path = project_root / "build" / "OpenModeling.spec"
    build_common.generate_pyinstaller_spec(
        project_root,
        spec_path,
        datas=datas,
        hiddenimports=hiddenimports,
        app_name=APP_NAME,
        optimize=optimize,
        strip=strip,
        upx=upx,
        console=False,
        disable_windowed_traceback=disable_windowed_traceback,
    )

    if use_cython:
        build_common.compile_cython_modules(project_root)

    cmd: list[str] = [
        str(python),
        "-m",
        "PyInstaller",
        str(spec_path),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(project_root / "dist"),
        "--workpath",
        str(project_root / "build"),
    ]

    print("Building release bundle...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=project_root)

    if use_cython:
        build_common.cleanup_cython_modules(project_root)

    if result.returncode != 0:
        raise RuntimeError("PyInstaller build failed")

    if not dist_dir.exists():
        raise RuntimeError(f"Expected dist directory not found: {dist_dir}")

    # Ensure default config files exist at the project root before bundling.
    get_config()

    # PyInstaller places data files inside _internal. Expose the user-facing
    # demos and default config files at the top level of the bundle.
    _internal = dist_dir / "_internal"
    demos_src = _internal / "demos"
    if demos_src.exists():
        shutil.copytree(demos_src, dist_dir / "demos", dirs_exist_ok=True)
    shutil.copy2(project_root / "om-gui.conf", dist_dir / "om-gui.conf")
    shutil.copy2(project_root / "om-engine.conf", dist_dir / "om-engine.conf")
    shutil.copy2(project_root / "version-manual.txt", dist_dir / "version-manual.txt")
    shutil.copy2(project_root / "version.txt", dist_dir / "version.txt")

    return dist_dir


def _stage_om_home(project_root: Path, dist_dir: Path) -> None:
    """Stage the project's local ./.om/ into the bundle, excluding sessions."""
    om_home = project_root / ".om"
    om_dest = dist_dir / ".om"
    om_dest.mkdir(exist_ok=True)

    # Copy existing local OM data except sessions.
    if om_home.exists():
        for item in om_home.iterdir():
            if item.name == "sessions":
                continue
            dest = om_dest / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Ensure the canonical subdirectories exist.
    for subdir in ("config", "toolbars", "macros", "exports", "recordings", "udf"):
        (om_dest / subdir).mkdir(exist_ok=True)


def _write_desktop_file(dist_dir: Path) -> None:
    """Write a portable .desktop file that can be launched from the bundle."""
    desktop = dist_dir / f"{APP_NAME}.desktop"
    desktop.write_text(
        """[Desktop Entry]
Name=OpenModeling
Comment=Dimensional calculation engine
Exec=bash -c 'cd "$(dirname %k)" && exec ./OpenModeling'
Type=Application
Terminal=false
Icon=OpenModeling
Categories=Office;Finance;Spreadsheet;
""",
        encoding="utf-8",
    )
    # Make the .desktop file executable so it can be launched directly.
    desktop.chmod(0o755)


def _write_install_desktop_script(dist_dir: Path) -> None:
    """Write a script that installs the .desktop entry and icon into ~/.local."""
    script = dist_dir / "install-desktop-entry.sh"
    script.write_text(
        r"""#!/bin/bash
set -e

BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
APPS_DIR="$HOME/.local/share/applications"
OM_HOME_DIR="$HOME/.om"

mkdir -p "$ICON_DIR"
mkdir -p "$APPS_DIR"
mkdir -p "$OM_HOME_DIR"

cp "$BUNDLE_DIR/_internal/assets/logo/taskbar-icon.png" "$ICON_DIR/OpenModeling.png"

cat > "$APPS_DIR/OpenModeling.desktop" <<EOF
[Desktop Entry]
Name=OpenModeling
Comment=Dimensional calculation engine
Exec=$BUNDLE_DIR/OpenModeling
Type=Application
Terminal=false
Icon=$ICON_DIR/OpenModeling.png
Categories=Office;Finance;Spreadsheet;
EOF

# Copy bundled .om/ skeleton (without sessions) into the user's OM_HOME.
if [ -d "$BUNDLE_DIR/.om" ]; then
    for dir in "$BUNDLE_DIR"/.om/*/; do
        subdir=$(basename "$dir")
        if [ "$subdir" = "sessions" ]; then
            continue
        fi
        mkdir -p "$OM_HOME_DIR/$subdir"
        cp -a "$dir/." "$OM_HOME_DIR/$subdir/"
    done
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR"
fi

echo "OpenModeling desktop entry installed."
echo "Look for it in your applications menu or run: $BUNDLE_DIR/OpenModeling"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _write_readme(dist_dir: Path, tarball_name: str) -> None:
    readme = dist_dir / "README.txt"
    readme.write_text(
        f"""OpenModeling Alpha {VERSION}
==============================

A dimensional calculation engine: build with cubes, dimensions, groups, and
rules, then explore through a spreadsheet-like grid.

Extract
-------

  tar -xzf {tarball_name} -C /path/to/install

Run
---

  ./OpenModeling

This starts the GUI with the bundled multi-cube financial demo workspace.
No installation, Python, or virtual environment is required.

Optional flags
--------------

  --gui-only              GUI with embedded runtime (same as default)
  --no-transport          Start the GUI without the remote client socket
  --load <file>           Open a specific .json workspace on startup
  --runtime               Start only the runtime server
  --gui                   Connect a GUI to an existing --runtime
  --repl                  Connect a REPL client to an existing --runtime

Demos
-----

The `demos/` folder contains sample workspaces:

  DEMO-01  multi-dimensional P&L
  DEMO-02  nested groups and roll-ups
  DEMO-03  multi-cube financial model
  DEMO-04  large dimension with infinite-scroll viewport

Open them from File > Open in the GUI.

System requirements
-------------------

  Linux x86_64
  A display server or X11 forwarding (Wayland/X11)
  ~290 MB of disk space (mostly Qt libraries and icon sets)

Desktop integration
-------------------

To add OpenModeling to your applications menu:

  ./install-desktop-entry.sh

This installs the launcher and icon into ~/.local/share/applications and
~/.local/share/icons. It also copies the bundled .om/ skeleton into ~/.om/.

Data and logs
-------------

The first run creates a workspace in the bundled `.om/` folder next to the
executable and logs in the `log/` folder next to the executable. The executable
itself does not need write permission to a system directory.

The bundled `.om/` folder contains default config/toolbar/macro/export/
recording/udf directories. Sessions are kept in `.om/sessions/` next to the
executable and are not bundled.

Feedback
--------

Please share feedback in the Show HN thread or file an issue with the build
or platform details.
""",
        encoding="utf-8",
    )


def _package_release(project_root: Path, dist_dir: Path, timestamp: str) -> Path:
    out_dir = project_root / "out"
    out_dir.mkdir(exist_ok=True)
    tarball_name = f"{APP_NAME}-{VERSION}-linux-x86_64-{timestamp}.tar.gz"
    tarball = out_dir / tarball_name

    # Remove any previous tarball so make_archive doesn't layer files.
    if tarball.exists():
        tarball.unlink()

    archive_stem = out_dir / f"{APP_NAME}-{VERSION}-linux-x86_64-{timestamp}"
    shutil.make_archive(str(archive_stem), "gztar", root_dir=dist_dir, base_dir=".")
    return tarball


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a standalone Linux release tarball for OpenModeling."
    )
    parser.add_argument(
        "--cython",
        action="store_true",
        help="Compile selected engine modules to Cython C extensions.",
    )
    parser.add_argument(
        "--protected",
        action="store_true",
        help="Enable PyInstaller protection/optimization flags (optimize=2, strip, no UPX, disable windowed traceback).",
    )
    args = parser.parse_args()

    project_root = _project_root()
    timestamp = _build_timestamp()
    tarball_name = f"{APP_NAME}-{VERSION}-linux-x86_64-{timestamp}.tar.gz"

    dist_dir = _build_pyinstaller(
        project_root, use_cython=args.cython, protected=args.protected
    )
    _stage_om_home(project_root, dist_dir)
    _write_desktop_file(dist_dir)
    _write_install_desktop_script(dist_dir)
    _write_readme(dist_dir, tarball_name)
    tarball = _package_release(project_root, dist_dir, timestamp)
    print(f"\nRelease ready: {tarball}")
    print(f"Extract with: tar -xzf {tarball.name} -C /path/to/install")
    print(f"Run with:     ./{APP_NAME}")
    print(f"Install menu: ./install-desktop-entry.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
