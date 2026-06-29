"""Timeline Widget Configuration.

This module contains configuration options for the timeline widget.
All options are in ALL_CAPS as constants.
"""

# ===================================================================
# Root Color Options
# ===================================================================
TIMELINE_ROOT_OVERRIDE = True  # Override root color with custom value
TIMELINE_ROOT_COLOUR = "#0303ee"  # Custom root color (blue)

# ===================================================================
# Line Thickness Options
# ===================================================================
TIMELINE_LINE_THICKNESS_OVERRIDE = True  # Override default line thickness
TIMELINE_LINE_THICKNESS = 8  # Line thickness in pixels
TIMELINE_NODE_SIZE_OVERRIDE = True  # Override default node size
TIMELINE_NODE_SIZE = 12  # Node size in pixels

# ===================================================================
# Behavior Options
# ===================================================================
TIMELINE_SINGLE_BRANCH_ONLY = True  # Only show single branch at a time (collapses other branches)
TIMELINE_ANIMATE_TRANSITIONS = True  # Animate branch transitions

# ===================================================================
# Debug Options
# ===================================================================
TIMELINE_DEBUG_ROOT_FORK = False  # Enable display of root fork & related info
TIMELINE_DEBUG_OPEN_FORKS_STATS = True  # Enable display of open forks statistics
TIMELINE_DEBUG_TOOLTIPS = True  # Enable debug tooltips with detailed info
TIMELINE_DEBUG_MOUSE = True  # Enable mouse event debug logging
TIMELINE_FORK_METADATA = False  # Enable fork metadata display
TIMELINE_CANVAS_SHOW = False  # Show red canvas border debug line

