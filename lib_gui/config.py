"""GUI-level configuration constants.

These are plain Python values rather than file-based config because they
govern internal GUI behavior, not user preferences.
"""

# Maximum number of cell / row / col keys sent to the engine for a
# selection-stats query.  Prevents the GUI main thread from blocking on
# huge payload construction.
SELECTION_STATS_MAX_PAYLOAD_KEYS = 10_000

# Seconds between heartbeat pings for remote transport clients.
# A shorter interval detects disconnects faster; longer reduces chatter.
HEARTBEAT_INTERVAL_SECONDS = 5.0

# Seconds to wait for a transport reply before giving up.
# Must be longer than the slowest command (e.g. loading a large workspace).
TRANSPORT_TIMEOUT_SECONDS = 300.0
