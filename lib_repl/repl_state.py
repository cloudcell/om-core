"""Thread-safe REPL state used by the prompt_toolkit status bar.

Background engine events update this object. Only the prompt_toolkit
render cycle reads from it — no async stdout printing.
"""

import threading

from .config import DISC_FG


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

    # -- rendering --------------------------------------------------------

    def render(self) -> str:
        """Return a compact HTML-formatted status string."""
        with self._lock:
            parts = []
            parts.append("<b> conn </b>" if self._connected else f"<style fg='{DISC_FG}'><b> disc </b></style>")
            parts.append(f" mt:{'on' if self._mt_recompute else 'off'} ")
            if self._dirty_count:
                parts.append(f"dirty:{self._dirty_count}")
            return "|".join(parts) if parts else ""
