#!/usr/bin/env python3
r"""Build a standalone Windows release zip for OpenModeling.

This script must be run on Windows (or in a Windows CI runner) because
PyInstaller produces platform-specific executables.

Usage (on Windows, in a venv with PyInstaller installed):
    .\venv\Scripts\activate
    python scripts\build_release_windows.py
    python scripts\build_release_windows.py --cython
    python scripts\build_release_windows.py --protected
    python scripts\build_release_windows.py --cython --protected

Produces:
    out\windows\OpenModeling-<version>-windows-x86_64-<timestamp>.zip

The release is a one-directory PyInstaller bundle with OpenModeling.exe,
bundled demo workspaces, default configs, and a README.

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
import zipfile
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
    return project_root / "venv" / "Scripts" / "python.exe"


def _latest_demos(project_root: Path) -> list[Path]:
    """Return the newest demo file for each DEMO-NN category."""
    groups: dict[str, list[Path]] = {}
    for path in sorted(project_root.glob("DEMO-*.json")):
        name = path.stem
        if not name.startswith("DEMO-"):
            continue
        prefix = name.split("--")[0] if "--" in name else name
        groups.setdefault(prefix, []).append(path)
    demos: list[Path] = []
    for prefix in sorted(groups):
        demos.append(sorted(groups[prefix])[-1])
    return demos


def _add_data(path: Path, dest: str) -> str:
    """Format an --add-data argument for the current platform."""
    # PyInstaller uses ';' on Windows and ':' on other platforms.
    sep = ";" if sys.platform == "win32" else ":"
    return f"{path}{sep}{dest}"


def _build_pyinstaller(
    project_root: Path,
    use_cython: bool = False,
    protected: bool = False,
) -> Path:
    if sys.platform != "win32":
        raise RuntimeError(
            "Windows builds must be produced on Windows (or via a Windows CI runner). "
            "PyInstaller cannot cross-compile from Linux to Windows."
        )

    python = _venv_python(project_root)
    if not python.exists():
        raise RuntimeError(f"Virtual environment Python not found: {python}")

    dist_dir = project_root / "dist" / "windows" / APP_NAME
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

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

    optimize = 2 if protected else 0
    strip = protected
    upx = not protected
    disable_windowed_traceback = protected

    spec_path = project_root / "build" / "windows" / "OpenModeling.spec"
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
        str(project_root / "dist" / "windows"),
        "--workpath",
        str(project_root / "build" / "windows"),
    ]

    print("Building Windows release bundle...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=project_root)

    if use_cython:
        build_common.cleanup_cython_modules(project_root)

    if result.returncode != 0:
        raise RuntimeError("PyInstaller Windows build failed")

    if not dist_dir.exists():
        raise RuntimeError(f"Expected dist directory not found: {dist_dir}")

    # Ensure default config files exist at the project root before bundling.
    get_config()

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
    r"""Stage the project's local ./.om/ into the bundle, excluding sessions."""
    om_home = project_root / ".om"
    om_dest = dist_dir / ".om"
    om_dest.mkdir(exist_ok=True)

    if om_home.exists():
        for item in om_home.iterdir():
            if item.name == "sessions":
                continue
            dest = om_dest / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    for subdir in ("config", "toolbars", "macros", "exports", "recordings", "udf"):
        (om_dest / subdir).mkdir(exist_ok=True)


def _write_install_script(dist_dir: Path) -> None:
    """Write a PowerShell script that installs a Start Menu shortcut."""
    script = dist_dir / "Install-StartMenuShortcut.ps1"
    script.write_text(
        r"""# Install OpenModeling into the Windows Start Menu and copy the bundled .om/ skeleton.
$BundleDir = $PSScriptRoot
$Programs = [Environment]::GetFolderPath('StartMenu') | Join-Path -ChildPath 'Programs'
$ShortcutPath = Join-Path $Programs 'OpenModeling.lnk'
$IconPath = Join-Path $BundleDir '_internal\assets\logo\taskbar-icon.png'
$OmHome = Join-Path $env:USERPROFILE '.om'

New-Item -ItemType Directory -Force -Path $Programs | Out-Null
New-Item -ItemType Directory -Force -Path $OmHome | Out-Null

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $BundleDir 'OpenModeling.exe'
$Shortcut.IconLocation = $IconPath
$Shortcut.Save()

if (Test-Path "$BundleDir\.om") {
    Get-ChildItem -Path "$BundleDir\.om" -Directory | Where-Object { $_.Name -ne 'sessions' } | ForEach-Object {
        $Dest = Join-Path $OmHome $_.Name
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Copy-Item -Path "$($_.FullName)\*" -Destination $Dest -Recurse -Force
    }
}

Write-Host "OpenModeling Start Menu shortcut installed."
Write-Host "Look for it in the Start Menu, or run: $(Join-Path $BundleDir 'OpenModeling.exe')"
""",
        encoding="utf-8",
    )


def _write_readme(dist_dir: Path, zip_name: str) -> None:
    readme = dist_dir / "README.txt"
    readme.write_text(
        rf"""OpenModeling Alpha {VERSION}
==============================

A dimensional calculation engine: build with cubes, dimensions, groups, and
rules, then explore through a spreadsheet-like grid.

Extract
-------

  Expand-Archive -Path {zip_name} -DestinationPath C:\path\to\install

Run
---

Double-click OpenModeling.exe or run from a terminal:

  OpenModeling.exe

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

  Windows 10/11 x86_64
  ~350 MB of disk space (mostly Qt libraries and icon sets)

Start Menu shortcut
-------------------

Run from PowerShell with execution policy bypass:

  powershell -ExecutionPolicy Bypass -File Install-StartMenuShortcut.ps1

This creates a Start Menu entry for OpenModeling, installs the taskbar icon,
and copies the bundled .om/ skeleton into %USERPROFILE%\.om\.

Data and logs
-------------

The first run creates a workspace in the bundled `.om\` folder next to the
executable and logs in the `log\` folder next to the executable.

The bundled `.om\` folder contains default config\toolbar\macro\export\
recording\udf directories. Sessions are kept in `.om\sessions\` next to the
executable and are not bundled.

Feedback
--------

Please share feedback in the Show HN thread or file an issue with the build
or platform details.
""",
        encoding="utf-8",
    )


def _package_release(project_root: Path, dist_dir: Path, timestamp: str) -> Path:
    out_dir = project_root / "out" / "windows"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{APP_NAME}-{VERSION}-windows-x86_64-{timestamp}.zip"
    zip_path = out_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in dist_dir.rglob("*"):
            arcname = path.relative_to(dist_dir).as_posix()
            if path.is_dir():
                # Ensure empty directories are recorded.
                zf.writestr(arcname + "/", "")
            else:
                zf.write(path, arcname)

    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a standalone Windows release zip for OpenModeling."
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
    zip_name = f"{APP_NAME}-{VERSION}-windows-x86_64-{timestamp}.zip"

    dist_dir = _build_pyinstaller(
        project_root, use_cython=args.cython, protected=args.protected
    )
    _stage_om_home(project_root, dist_dir)
    _write_install_script(dist_dir)
    _write_readme(dist_dir, zip_name)
    zip_path = _package_release(project_root, dist_dir, timestamp)
    print(f"\nRelease ready: {zip_path}")
    print(f"Extract with: Expand-Archive -Path {zip_path.name} -DestinationPath C:\\path\\to\\install")
    print(rf"Run with:     .\{APP_NAME}\OpenModeling.exe")
    print(rf"Install menu: .\{APP_NAME}\Install-StartMenuShortcut.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
