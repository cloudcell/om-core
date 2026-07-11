from __future__ import annotations

import logging
import sys


def setup_logging(
    level: int = logging.INFO,
    console_level: int | None = None
) -> logging.Logger:
    """Setup root logger for console output only.

    File logging is handled by dedicated service loggers
    (REPL, GUI, BUS, ENGINE) so each writes to its own separate log.

    Args:
        level: Default logging level
        console_level: Level for console output (default: INFO)

    Returns:
        Root logger
    """
    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console only.  File logging is handled by dedicated service loggers
    # (REPL, GUI, BUS, ENGINE) so each writes to its own separate log.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level if console_level is not None else level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    root_logger.debug("Root logging initialized (console only)")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
