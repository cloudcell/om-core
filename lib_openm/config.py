"""Engine-level configuration constants.

These values govern engine behaviour such as iteration limits,
cache sizes, and sampling thresholds.  They are not user-editable
per-workspace settings; change them here and restart.
"""

# Maximum number of cells cmd_selection_stats will evaluate before
# sampling uniformly.  Large values improve accuracy on huge grids
# but increase query latency when cells are rule-evaluated.
SELECTION_STATS_MAX_CELLS: int = 10_000_000

# Threshold (seconds) above which rule evaluation is logged as slow.
SLOW_LOG_THRESHOLD: float = 0.01
