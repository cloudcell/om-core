"""GUI-wide visual constants for reuse across client code.

These are plain Python constants rather than config-file settings because they
are not user-editable and must stay in sync across all GUI components.
"""

# Braille spinner frames for status-bar progress indicators.
# Ordered counter-clockwise for a crawling-snake effect.
BRAILLE_SPINNER_FRAMES: list[str] = [
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
]

# Dense 8-dot (4×2) fallback for environments that support it.
BRAILLE_SPINNER_FRAMES_DENSE: list[str] = [
    "⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷",
]

# Plain ASCII line spinner — useful when Unicode braille does not render
# or when testing whether display issues are charset-related.
LINE_SPINNER_FRAMES: list[str] = [
    "/", "-", "\\", "|",
]
