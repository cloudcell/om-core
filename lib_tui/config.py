"""TUI color and style configuration.

Centralizes all prompt_toolkit colors used across the TUI layer.
"""

# -- top label bar ---------------------------------------------------------
LABEL_FG = "#000000"    # dark blue background
LABEL_BG = "#FFA500"    # orange text

# -- status line -----------------------------------------------------------
STATUS_FG = "grey"   # text color on the status bar
STATUS_BG = "#000032"   # background color of the status bar

# -- prompt ----------------------------------------------------------------
PROMPT_FG = "#99ff55"     # om> prefix color
PROMPT_BG = ""          # default terminal background

# -- completion menu -------------------------------------------------------
COMPLETION_FG = "#000000"
COMPLETION_BG = "#aaaaaa"
COMPLETION_SELECTED_FG = "#ffffff"
COMPLETION_SELECTED_BG = "#00003f"

# -- output / transcript -----------------------------------------------------
OUTPUT_FG = ""          # default
OUTPUT_BG = ""          # default

# -- command echo separator --------------------------------------------------
# "blank"  -> empty line before each om> prompt echo
# "rule"   -> thin horizontal rule line
COMMAND_SEPARATOR = "rule"

# -- mouse support -----------------------------------------------------------
# True  -> clickable scrollbar, completion menu, scroll wheel
#         (use Shift+click/drag for text selection in most terminals)
# False -> native terminal mouse text selection, no click scrolling
MOUSE_SUPPORT = True

# -- buffer limits ---------------------------------------------------------
MAX_BUFFER_LINES = 100_000   # trim oldest lines when exceeded
MAX_MONITOR_MESSAGES = 10_000  # trim oldest messages when exceeded

# -- monitor overlay -------------------------------------------------------
MONITOR_LABEL_FG = "#ffffff"
MONITOR_LABEL_BG = "#000032"
MONITOR_SELECTED_FG = "#ffffff"
MONITOR_SELECTED_BG = "#00003f"
MONITOR_NORMAL_FG = ""
MONITOR_NORMAL_BG = ""
MONITOR_LOG_FG = ""
MONITOR_LOG_BG = ""
MONITOR_FOOTER_FG = "grey"
MONITOR_FOOTER_BG = "#000032"
MONITOR_DIVIDER_FG = "grey"
MONITOR_DIVIDER_BG = ""

MAX_MONITOR_MESSAGES = 5000   # per-topic ring buffer cap (total across all topics)
MAX_MONITOR_TOPICS = 200     # max distinct topics before eviction

# -- highlight styles ------------------------------------------------------
HIGHLIGHT_KEYWORD  = "#0000aa bold"
HIGHLIGHT_STRING   = "#005500"
HIGHLIGHT_NUMBER   = "#aa5500"
HIGHLIGHT_ERROR    = "#aa0000 bold"
