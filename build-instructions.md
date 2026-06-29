# Instructions

## Linux

### Build the Linux release

```bash
source ./venv/bin/activate
python scripts/build_release.py
```

Optional flags:

```bash
python scripts/build_release.py --cython      # compile engine modules to C extensions
python scripts/build_release.py --protected   # optimize=2, strip, no UPX, disable windowed traceback
python scripts/build_release.py --cython --protected
```

### Extract and run on Linux

```bash
tar -xzf OpenModeling-XX.X.X-linux-x86_64-YYYYMMDD-HHMMSS.tar.gz -C /path/to/install
cd /path/to/install
./OpenModeling
./install-desktop-entry.sh   # adds launcher + icon to your applications menu
```

## Windows

> PyInstaller builds are platform-specific. The Windows release must be built
> on Windows (or in a Windows CI runner) — it cannot be cross-built from Linux.

### Build the Windows release

```powershell
.\venv\Scripts\activate
python scripts\build_release_windows.py
```

Optional flags:

```powershell
python scripts\build_release_windows.py --cython      # compile engine modules to C extensions
python scripts\build_release_windows.py --protected   # optimize=2, strip, no UPX, disable windowed traceback
python scripts\build_release_windows.py --cython --protected
```

Output is written to `out\windows\OpenModeling-XX.X.X-windows-x86_64-YYYYMMDD-HHMMSS.zip`.

### Extract and run on Windows

```powershell
Expand-Archive -Path OpenModeling-XX.X.X-windows-x86_64-YYYYMMDD-HHMMSS.zip -DestinationPath C:\path\to\install
cd C:\path\to\install\OpenModeling
.\OpenModeling.exe
powershell -ExecutionPolicy Bypass -File Install-StartMenuShortcut.ps1   # adds Start Menu entry and icon
```
