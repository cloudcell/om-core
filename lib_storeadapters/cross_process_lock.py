"""Cross-process file lock.

Uses fcntl on Unix-like systems and Windows LockFileEx via ctypes on Windows.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path
from typing import Any, IO


class CrossProcessLock:
    """Advisory cross-process lock backed by a file.

    The lock is process-safe (threading.Lock) and process-safe (OS file lock).
    Closing the file handle or exiting the process releases the OS lock.
    """

    def __init__(self, lock_path: str | Path) -> None:
        self._lock_path = Path(lock_path)
        self._thread_lock = threading.Lock()
        self._fd: IO[Any] | None = None

    def acquire(self) -> None:
        """Acquire the exclusive cross-process lock, blocking until available."""
        self._thread_lock.acquire()
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = open(self._lock_path, "w")
            if sys.platform == "win32":
                _lock_windows(self._fd.fileno())
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX)
        except Exception:
            self._thread_lock.release()
            raise

    def release(self) -> None:
        """Release the exclusive cross-process lock."""
        try:
            if self._fd is not None:
                if sys.platform == "win32":
                    _unlock_windows(self._fd.fileno())
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                self._fd.close()
                self._fd = None
        finally:
            self._thread_lock.release()

    def __enter__(self) -> "CrossProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


class _OVERLAPPED(ctypes.Structure):
    """Minimal OVERLAPPED layout for LockFileEx / UnlockFileEx.

    ctypes.wintypes does not expose this on every Windows build, so we define it
    explicitly. The size and hEvent offset match the Windows SDK struct.
    """

    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", ctypes.c_ulong),
        ("OffsetHigh", ctypes.c_ulong),
        ("hEvent", ctypes.c_void_p),
    ]


def _lock_windows(fd: int) -> None:
    """Acquire an exclusive Windows file lock on the whole file."""
    import msvcrt

    handle = msvcrt.get_osfhandle(fd)
    overlapped = _OVERLAPPED()
    overlapped.Offset = 0
    overlapped.OffsetHigh = 0
    overlapped.hEvent = 0
    if not ctypes.windll.kernel32.LockFileEx(
        handle,
        0x00000002,  # LOCKFILE_EXCLUSIVE_LOCK
        0,
        0xFFFFFFFF,
        0xFFFFFFFF,
        ctypes.byref(overlapped),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _unlock_windows(fd: int) -> None:
    """Release the Windows file lock on the whole file."""
    import msvcrt

    handle = msvcrt.get_osfhandle(fd)
    overlapped = _OVERLAPPED()
    overlapped.Offset = 0
    overlapped.OffsetHigh = 0
    overlapped.hEvent = 0
    if not ctypes.windll.kernel32.UnlockFileEx(
        handle,
        0,
        0xFFFFFFFF,
        0xFFFFFFFF,
        ctypes.byref(overlapped),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
