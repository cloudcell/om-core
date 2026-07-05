"""Compatibility re-export for EventPublisher.

The canonical port definition now lives in lib_openm.ports. Existing imports
from lib_openm.event_publisher continue to work but new code should import
from lib_openm.ports.
"""

from __future__ import annotations

from lib_openm.ports import EventPublisher

__all__ = ["EventPublisher"]
