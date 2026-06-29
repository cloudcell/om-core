"""Configuration for datastore behavior.

Centralized configuration for snapshot storage modes and delta engine settings.

MASTER SWITCH:
  Setting DATASTORE_SAVEDELTAS = False disables ALL delta functionality,
  ignoring all other options below. Full snapshots are saved every time.
"""

# MASTER SWITCH: When False, ignores all other delta options and saves full snapshots only
# When True: save deltas between snapshots (diffs) with periodic full snapshots
DATASTORE_SAVEDELTAS = True

# Maximum number of deltas to chain before forcing a full snapshot
# Prevents long delta chains that slow down restore operations
# Set to 0 to disable automatic chain reset (no max - not recommended)
DATASTORE_MAX_DELTA_CHAIN = 10  # default was 50

# Force full snapshot every N automatic saves
# Ensures periodic full checkpoints for reliability
# Set to 0 to disable periodic full snapshots (only chain reset applies)
DATASTORE_FULL_SNAPSHOT_EVERY = 20

# Enable checksum verification for delta and full snapshots
# When True: verifies data integrity during save/load
# When False: skips checksum computation/verification (slightly faster)
DATASTORE_VERIFY_CHECKSUMS = True

# Compression level for stored payloads (0-9, where 9 is max compression)
# Only applies to full snapshots; deltas are stored as-is for speed
DATASTORE_COMPRESSION_LEVEL = 6
