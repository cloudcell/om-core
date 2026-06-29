"""Thread-safe REPL state used by the prompt_toolkit status bar.

Background engine events update this object. Only the prompt_toolkit
render cycle reads from it — no async stdout printing.
"""

import threading
from typing import Any

from .config import DISC_FG, NOTICE_FG, NOTICE_BG


class ReplState:
    """Compact, thread-safe REPL status holder.

    Updated from bus-event callbacks; read by the prompt_toolkit
    bottom_toolbar render callback.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connected = True
        self._mt_recompute = False
        self._dirty_count = 0
        self._pending_notices = 0

    # -- property accessors (thread-safe) --------------------------------

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @connected.setter
    def connected(self, val: bool) -> None:
        with self._lock:
            self._connected = val

    @property
    def mt_recompute(self) -> bool:
        with self._lock:
            return self._mt_recompute

    @mt_recompute.setter
    def mt_recompute(self, val: bool) -> None:
        with self._lock:
            self._mt_recompute = val

    @property
    def dirty_count(self) -> int:
        with self._lock:
            return self._dirty_count

    @dirty_count.setter
    def dirty_count(self, val: int) -> None:
        with self._lock:
            self._dirty_count = val

    @property
    def pending_notices(self) -> int:
        with self._lock:
            return self._pending_notices

    @pending_notices.setter
    def pending_notices(self, val: int) -> None:
        with self._lock:
            self._pending_notices = val

    def increment_notices(self, n: int = 1) -> None:
        with self._lock:
            self._pending_notices += n

    def reset_notices(self) -> None:
        with self._lock:
            self._pending_notices = 0

    # -- rendering --------------------------------------------------------

    def render(self) -> str:
        """Return a compact HTML-formatted status string."""
        with self._lock:
            parts = []
            parts.append("<b> conn </b>" if self._connected else f"<style fg='{DISC_FG}'><b> disc </b></style>")
            parts.append(f" mt:{'on' if self._mt_recompute else 'off'} ")
            if self._dirty_count:
                parts.append(f"dirty:{self._dirty_count}")
            if self._pending_notices:
                parts.append(f"<style bg='{NOTICE_BG}' fg='{NOTICE_FG}'> notices:{self._pending_notices} </style>")
            return "|".join(parts) if parts else ""
