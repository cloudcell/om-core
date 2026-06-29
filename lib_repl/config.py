"""REPL color and style configuration.

Centralizes all prompt_toolkit colors used across the REPL UI layer.
"""

# -- bottom-toolbar style (Style.from_dict) --------------------------------
TOOLBAR_FG = "#000055"   # text color on the status bar
TOOLBAR_BG = "#888888"      # background color of the status bar

# -- top-toolbar style (Style.from_dict) -----------------------------------
HEADER_FG = "#FFA500"    # orange title text

# -- inline HTML colors (ReplState.render) ---------------------------------
DISC_FG = "red"          # disconnected state
NOTICE_FG = "#FFA500"    # pending notice count (orange)
NOTICE_BG = "#000000"    # pending notice background
