"""Plugin discovery — walks the plugins/ directory and finds BasePlugin subclasses."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
from pathlib import Path

from .base import BasePlugin, DataSource, Delivery, Hook, Tool

logger = logging.getLogger(__name__)

# The four category ABCs that should NOT be registered directly
_ABSTRACT_BASES = {BasePlugin, DataSource, Tool, Delivery, Hook}


def discover_plugins(plugins_dir: Path | None = None) -> list[type[BasePlugin]]:
    """Walk the plugins directory and return all concrete BasePlugin subclasses.

    Each .py file is imported in isolation — a broken file doesn't prevent
    other plugins from loading.
    """
    if plugins_dir is None:
        env_dir = os.environ.get("PLUGINS_DIR")
        if env_dir:
            plugins_dir = Path(env_dir)
        else:
            # Default: plugins/ directory at the project root
            plugins_dir = Path(__file__).resolve().parent.parent.parent.parent / "plugins"

    if not plugins_dir.is_dir():
        logger.info("No plugins directory found at %s", plugins_dir)
        return []

    found = []
    for plugin_file in sorted(plugins_dir.glob("*.py")):
        if plugin_file.name.startswith("_"):
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_file.stem}", plugin_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning("Failed to import %s: %s", plugin_file.name, e)
            continue

        # Find all concrete BasePlugin subclasses in the module
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BasePlugin) and obj not in _ABSTRACT_BASES:
                found.append(obj)
                logger.debug("Discovered plugin class: %s in %s", _name, plugin_file.name)

    return found
