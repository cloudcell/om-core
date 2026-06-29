from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any


# Known plugins for frozen/PyInstaller bundles where pkgutil.iter_modules
# cannot discover subpackages from the PYZ archive. Keep this in sync with the
# packages under lib_plugins/.
_KNOWN_PLUGIN_PACKAGES: list[str] = ["excel"]


def load_plugins(main_window: Any, plugins_menu: Any) -> tuple[list[str], list[str]]:
    loaded: list[str] = []
    errors: list[str] = []
    plugins_root = Path(__file__).resolve().parent

    discovered = [
        mod.name
        for mod in pkgutil.iter_modules([str(plugins_root)])
        if mod.ispkg and not mod.name.startswith("_")
    ]

    # In PyInstaller bundles the loader module lives in the PYZ archive, so
    # pkgutil.iter_modules cannot see the real lib_plugins directory. Fall back
    # to the hard-coded list so plugin menus still appear in release builds.
    if not discovered:
        discovered = list(_KNOWN_PLUGIN_PACKAGES)

    for name in discovered:
        if name.startswith("_"):
            continue
        module_name = f"lib_plugins.{name}.plugin"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive startup path
            errors.append(f"{name}: import failed: {exc}")
            continue
        register = getattr(module, "register_plugin", None)
        if not callable(register):
            continue
        try:
            register(main_window, plugins_menu)
            loaded.append(name)
        except Exception as exc:  # pragma: no cover - defensive startup path
            errors.append(f"{name}: register failed: {exc}")

    return loaded, errors
