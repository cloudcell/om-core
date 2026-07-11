"""Configuration management for OM Core.

Provides centralized access to om-gui.conf and om-engine.conf settings.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Default configuration file paths
PROJECT_ROOT = Path(__file__).parent.parent
GUI_CONFIG_PATH = PROJECT_ROOT / "om-gui.conf"
ENGINE_CONFIG_PATH = PROJECT_ROOT / "om-engine.conf"


class ConfigManager:
    """Manages GUI and Engine configuration files."""

    _instance: Optional["ConfigManager"] = None
    _gui_config: configparser.ConfigParser
    _engine_config: configparser.ConfigParser

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._gui_config = configparser.ConfigParser()
            cls._instance._engine_config = configparser.ConfigParser()
            cls._instance._load_configs()
        return cls._instance

    def _load_configs(self) -> None:
        """Load or create configuration files."""
        # Create default configs if they don't exist
        if not GUI_CONFIG_PATH.exists():
            self._create_default_gui_config()
        if not ENGINE_CONFIG_PATH.exists():
            self._create_default_engine_config()

        # Read the configs
        self._gui_config.read(GUI_CONFIG_PATH, encoding="utf-8")
        self._engine_config.read(ENGINE_CONFIG_PATH, encoding="utf-8")

    def _create_default_gui_config(self) -> None:
        """Create default om-gui.conf file."""
        default_content = '''# OM Core GUI Configuration File (om-gui.conf)
# This file contains all GUI-related settings for the OM application

[window]
default_width = 1400
default_height = 900
min_width = 800
min_height = 600

[layout]
# Dock widget areas: Left, Right, Top, Bottom
dock_browser_area = "Left"
dock_info_area = "Left"
dock_format_area = "Left"
dock_performance_area = "Right"

# Default dock sizes (pixels)
dock_browser_width = 250
dock_info_width = 250
dock_format_width = 250
dock_performance_width = 280

# Splitter ratios (0.0 to 1.0)
main_splitter_ratio = 0.7

[appearance]
# Colors (hex format)
status_bar_text_color = "#000000"
status_bar_background = "#f0f0f0"
engine_indicator_bg = "#e8e8e8"
focus_indicator_color = "#333333"
truncation_warning_color = "#d32f2f"

# Font settings
font_family = "system"
font_size = 9

[status_bar]
# Status indicator settings
indicator_min_width = 220
indicator_contents_margins_left = 6
indicator_contents_margins_top = 0
indicator_contents_margins_right = 0
indicator_contents_margins_bottom = 0

# Engine indicator settings
engine_indicator_padding_x = 8
engine_indicator_padding_y = 2
engine_indicator_border_radius = 4

[panels]
# Performance Watch panel
performance_auto_refresh = true
performance_refresh_interval_ms = 1000

# Calculation Flow panel
calculation_flow_default_depth = 2
calculation_flow_max_depth = 10
calculation_flow_max_precedents = 12

# Circular References panel
circular_refs_auto_refresh = true

[toolbox]
# Format toolbox settings
format_tab_default = "Background Color"

[gui]
# Show system elements (names beginning with '%') in the Model Browser, tabs, and selectors.
show_system_elements = false

[behavior]
# Auto-save settings
auto_save_enabled = false
auto_save_interval_minutes = 5

# Selection stats default
default_stats = ["avg", "sum"]

# Dependency tracking
default_dep_tracking = true

# Mouse scroll sensitivity (multiplier for scroll wheel events)
mouse_scroll_sensitivity = 1.0

[performance]
# Tile prefetch: max cells per side (1 to 256)
prefetch_max_tile_size = 8
# Pre-render thread pool size (1 to half of CPU cores)
prerender_thread_pool_size = 8
# Fetch and render value-only plain tiles first for instant visibility
prerender_plain_data = false

[profiler]
# On-demand GUI profiling limits and timeouts

# Maximum profiling duration a user may request via the `profile gui` command.
max_duration_seconds = 300

# Extra wait time added for short profiles (< long_profile_threshold_seconds)
# to cover GUI paint/recompute before the profiler report arrives.
short_headroom_seconds = 15

# Extra wait time added for long profiles (>= long_profile_threshold_seconds);
# needed when the Julia engine blocks the runtime during recalculation.
long_headroom_seconds = 60

# Duration threshold that switches from short_headroom_seconds to long_headroom_seconds.
long_profile_threshold_seconds = 10

[transport]
# Remote client transport defaults

# Default socket read timeout for the remote client (TUI/GUI) when waiting
# for a command or query reply from the runtime.
default_timeout_seconds = 30

# How often the remote client polls the runtime for subscribed bus events.
poll_interval_seconds = 0.1

# Default timeout for command bus request/reply inside the runtime.
bus_transport_timeout_seconds = 5

# Server-side per-connection socket read timeout.
server_timeout_seconds = 5

[debug]
# Debug flags (can be overridden by environment variables)
debug_gui = false
debug_flow_panel = false
debug_flow_graph = false
debug_calc_flow = false
'''
        with open(GUI_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(default_content)

    def _create_default_engine_config(self) -> None:
        """Create default om-engine.conf file."""
        default_content = '''# OM Engine Configuration File (om-engine.conf)
# This file contains all engine-related settings for the OM calculation engine

[engine]
# Default engine type: "python"
default_engine = "python"

[persistence]
# Whether to persist computed values (values calculated from formulas/rules)
# When false, only user-entered hardcoded values are saved to disk.
# Computed values can always be recalculated from the formulas.
persist_calculated_values = false

# Snapshot mode: manual (default) or auto.
# manual: snapshots created only by explicit command.
# auto: snapshot after every N dirty canonical model actions.
mode = manual
auto_snapshot_dirty_action_interval = 50

[calculation]
# Recalculation settings
incremental_recalc = true
auto_recalc = true
max_parallel_workers = 64

# Dependency tracking
dependency_tracking_default = true

# Formula evaluation
formula_cache_size = 10000
formula_eval_timeout_seconds = 30

[limits]
# Calculation flow limits
max_calculation_flow_depth = 10
default_calculation_flow_depth = 2
max_precedents_per_node = 12
max_dependents_per_node = 12
max_formula_trace_nodes = 100

# Circular reference limits
max_circular_ref_iterations = 1000
circular_ref_convergence_threshold = 1e-10

# Memory limits
max_cached_cells = 1000000
max_slice_cache_entries = 10000

[performance]
# Multi-threading
enable_multithreading = false
parallel_threshold = 24
reuse_worker_pool = true
mt_batch_size = 8

# Caching
cell_cache_enabled = true
slice_cache_enabled = true
function_cache_enabled = true

[formulas]
# Formula evaluation settings
strict_formula_syntax = false
case_insensitive_functions = true
support_excel_syntax = true

# Error handling
treat_errors_as_zeros = false
propagate_nan = true

[debug]
# Debug flags (can be overridden by environment variables)
flow_trace_debug = false
circular_ref_debug = false
formula_eval_debug = false
compute_trace_debug = false
'''
        with open(ENGINE_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(default_content)

    def get_gui(self, section: str, key: str, fallback: Any = None) -> Any:
        """Get a value from om-gui.conf.
        
        Args:
            section: Configuration section name
            key: Configuration key name
            fallback: Default value if key not found
            
        Returns:
            The configuration value, converted to appropriate type
        """
        try:
            value = self._gui_config.get(section, key)
            return self._convert_value(value)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_engine(self, section: str, key: str, fallback: Any = None) -> Any:
        """Get a value from om-engine.conf.
        
        Args:
            section: Configuration section name
            key: Configuration key name
            fallback: Default value if key not found
            
        Returns:
            The configuration value, converted to appropriate type
        """
        try:
            value = self._engine_config.get(section, key)
            return self._convert_value(value)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate Python type."""
        value = value.strip()
        value_lower = value.lower()
        
        # Boolean (handle both True/False and true/false)
        if value_lower in ("true", "yes", "1", "on"):
            return True
        if value_lower in ("false", "no", "0", "off"):
            return False
            
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
            
        # Float
        try:
            return float(value)
        except ValueError:
            pass
            
        # List (format: [item1, item2, item3])
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            items = []
            for item in inner.split(","):
                item = item.strip().strip('"\'')
                if item:
                    items.append(item)
            return items
            
        # String (strip quotes)
        return value.strip('"\'')

    def set_gui(self, section: str, key: str, value: Any) -> None:
        """Set a value in om-gui.conf and save."""
        if not self._gui_config.has_section(section):
            self._gui_config.add_section(section)
        self._gui_config.set(section, key, str(value))
        self._save_gui_config()

    def set_engine(self, section: str, key: str, value: Any) -> None:
        """Set a value in om-engine.conf and save."""
        if not self._engine_config.has_section(section):
            self._engine_config.add_section(section)
        self._engine_config.set(section, key, str(value))
        self._save_engine_config()

    def _save_gui_config(self) -> None:
        """Save om-gui.conf to disk."""
        with open(GUI_CONFIG_PATH, "w", encoding="utf-8") as f:
            self._gui_config.write(f)
            f.flush()
            os.fsync(f.fileno())

    def _save_engine_config(self) -> None:
        """Save om-engine.conf to disk."""
        with open(ENGINE_CONFIG_PATH, "w", encoding="utf-8") as f:
            self._engine_config.write(f)
            f.flush()
            os.fsync(f.fileno())

    def get_gui_section(self, section: str) -> Dict[str, Any]:
        """Get all key-value pairs from an om-gui.conf section."""
        try:
            return {k: self._convert_value(v) for k, v in self._gui_config.items(section)}
        except configparser.NoSectionError:
            return {}

    def get_engine_section(self, section: str) -> Dict[str, Any]:
        """Get all key-value pairs from an om-engine.conf section."""
        try:
            return {k: self._convert_value(v) for k, v in self._engine_config.items(section)}
        except configparser.NoSectionError:
            return {}


# Global config manager instance
_config: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get the global ConfigManager instance."""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config


# Convenience functions for common access patterns
def gui(section: str, key: str, fallback: Any = None) -> Any:
    """Quick access to om-gui.conf values."""
    return get_config().get_gui(section, key, fallback)


def engine(section: str, key: str, fallback: Any = None) -> Any:
    """Quick access to om-engine.conf values."""
    return get_config().get_engine(section, key, fallback)


def set_gui(section: str, key: str, value: Any) -> None:
    """Quick setter for om-gui.conf values."""
    return get_config().set_gui(section, key, value)


# Debug guard utilities for compute tracing
# ---------------------------------------------------------------------------

# Cache for environment variable lookups to avoid repeated os.environ access
_env_cache: Dict[str, bool] = {}


def is_compute_trace_enabled() -> bool:
    """Check if compute tracing debug is enabled.
    
    Priority (highest to lowest):
    1. OPENM_COMPUTE_TRACE environment variable
    2. engine.conf [debug] compute_trace_debug
    3. Default (False)
    
    Returns:
        True if compute tracing debug is enabled
    """
    # Check environment variable first (highest priority)
    env_val = os.environ.get("OPENM_COMPUTE_TRACE", "").lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    if env_val in ("0", "false", "no", "off"):
        return False
    
    # Fall back to config file
    return engine("debug", "compute_trace_debug", False)


def compute_trace(msg: str) -> None:
    """Print a compute trace debug message if tracing is enabled.
    
    Args:
        msg: The debug message to print
    """
    if is_compute_trace_enabled():
        print(f"[COMPUTE TRACE] {msg}")


def compute_trace_if(condition: bool, msg: str) -> None:
    """Print a compute trace debug message if tracing is enabled AND condition is true.
    
    Args:
        condition: Condition that must be true to print
        msg: The debug message to print
    """
    if condition and is_compute_trace_enabled():
        print(f"[COMPUTE TRACE] {msg}")
