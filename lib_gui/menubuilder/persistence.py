"""
Persistence layer for toolbar configurations.
Handles saving and loading toolbar configs to/from JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import ToolbarConfig, CategoryDef, DEFAULT_CATEGORIES, ToolboxConfig as ToolboxConfigNew, MenuItemDef


from lib_utils.paths import OM_TOOLBARS_DIR as DEFAULT_CONFIG_DIR


def _ensure_config_dir() -> Path:
    """Ensure the config directory exists."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR


def save_toolbar(config: ToolbarConfig, filename: str | None = None) -> Path:
    """
    Save a toolbar configuration to JSON.

    Args:
        config: The toolbar configuration to save
        filename: Optional filename (defaults to config.name + .json)

    Returns:
        Path to the saved file
    """
    config_dir = _ensure_config_dir()

    if filename is None:
        # Sanitize name for filesystem
        safe_name = config.name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        filename = f"{safe_name}.json"

    filepath = config_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    return filepath


def load_toolbar(filename: str | Path) -> ToolbarConfig:
    """
    Load a toolbar configuration from JSON.

    Args:
        filename: Name of file in config dir, or full path

    Returns:
        The loaded ToolbarConfig
    """
    if not Path(filename).is_absolute():
        filepath = _ensure_config_dir() / filename
    else:
        filepath = Path(filename)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ToolbarConfig.from_dict(data)


def list_saved_toolbars() -> List[tuple[str, Path]]:
    """
    List all saved toolbar configurations.

    Returns:
        List of (name, filepath) tuples
    """
    config_dir = _ensure_config_dir()
    toolbars = []

    for filepath in sorted(config_dir.glob("*.json")):
        try:
            config = load_toolbar(filepath)
            toolbars.append((config.name, filepath))
        except Exception:
            # Skip corrupted files
            continue

    return toolbars


def delete_toolbar(filename: str | Path) -> bool:
    """
    Delete a saved toolbar configuration.

    Args:
        filename: Name of file in config dir, or full path

    Returns:
        True if deleted, False if not found
    """
    if not Path(filename).is_absolute():
        filepath = _ensure_config_dir() / filename
    else:
        filepath = Path(filename)

    if filepath.exists():
        filepath.unlink()
        return True
    return False


def export_to_application_format(config: ToolbarConfig, filepath: Path) -> None:
    """
    Export toolbar config to the main application's menu format.
    This allows importing custom toolbars into the main OpenM app.
    """
    # Convert to simple format for main app integration
    export_data = {
        "version": "1.0",
        "toolbar": {
            "name": config.name,
            "buttons": [
                {
                    "id": btn.id,
                    "label": btn.label,
                    "icon": btn.icon,
                    "command_id": btn.command.id,
                    "category": btn.category,
                }
                for btn in config.buttons
            ]
        }
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)


def load_categories_from_file(filepath: Path) -> list[CategoryDef]:
    """
    Load custom button categories from a JSON file.
    If file doesn't exist, returns DEFAULT_CATEGORIES.
    """
    if not filepath.exists():
        return DEFAULT_CATEGORIES.copy()

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return [CategoryDef.from_dict(cat) for cat in data]
    elif isinstance(data, dict) and "categories" in data:
        return [CategoryDef.from_dict(cat) for cat in data["categories"]]

    return DEFAULT_CATEGORIES.copy()


# =============================================================================
# TOOLBOX CONFIGURATION - gui-toolbox.conf persistence
# =============================================================================

from lib_utils.paths import DEFAULT_TOOLBOX_CONFIG_PATH


def save_toolbox_config(config: ToolboxConfigNew, path: Path | None = None) -> Path:
    """
    Save toolbox configuration to gui-toolbox.conf.

    Args:
        config: The toolbox configuration to save
        path: Optional custom path (defaults to ~/.om/config/gui-toolbox.conf)

    Returns:
        Path to the saved file
    """
    filepath = path or DEFAULT_TOOLBOX_CONFIG_PATH
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        f.flush()  # Ensure data is written to disk immediately
        import os
        os.fsync(f.fileno())  # Force sync to filesystem

    return filepath


def load_toolbox_config(path: Path | None = None) -> ToolboxConfigNew:
    """
    Load toolbox configuration from gui-toolbox.conf.

    Args:
        path: Optional custom path (defaults to ~/.om/config/gui-toolbox.conf)

    Returns:
        The loaded ToolboxConfig, or a default empty config if file doesn't exist
    """
    filepath = path or DEFAULT_TOOLBOX_CONFIG_PATH

    if not filepath.exists():
        return ToolboxConfigNew()  # Return default empty config

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ToolboxConfigNew.from_dict(data)
