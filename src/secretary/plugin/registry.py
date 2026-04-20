"""Plugin registry — validates config, registers plugins, tracks failures."""

from __future__ import annotations

import logging
from typing import Any

from .base import BasePlugin, DataSource, Delivery, Hook, PluginCategory, Tool

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Discovers, validates, and categorizes plugins."""

    def __init__(self):
        self.data_sources: list[DataSource] = []
        self.tools: list[Tool] = []
        self.deliveries: list[Delivery] = []
        self.hooks: dict[str, list[Hook]] = {"pre_agent": [], "post_agent": []}
        self._failed: list[tuple[str, str]] = []

    def register(self, plugin_cls: type[BasePlugin], config: dict[str, Any]) -> None:
        """Validate config and register a plugin. Gracefully skip on failure."""
        name = getattr(plugin_cls, "name", plugin_cls.__name__)

        # Check required config keys
        missing = []
        for req in getattr(plugin_cls, "config_schema", []):
            if req.required and req.key not in config:
                missing.append(req.key)
        if missing:
            self._failed.append((name, f"Missing config: {missing}"))
            logger.info("Skipping %s: missing config keys %s", name, missing)
            return

        # Instantiate and initialize with error isolation
        try:
            instance = plugin_cls()
            instance.initialize(config)
        except Exception as e:
            self._failed.append((name, str(e)))
            logger.warning("Failed to initialize %s: %s", name, e)
            return

        # File into correct category
        match instance.category:
            case PluginCategory.DATA_SOURCE:
                self.data_sources.append(instance)
            case PluginCategory.TOOL:
                self.tools.append(instance)
            case PluginCategory.DELIVERY:
                self.deliveries.append(instance)
            case PluginCategory.HOOK:
                hook_point = getattr(instance, "hook_point", "pre_agent")
                self.hooks.setdefault(hook_point, []).append(instance)

        logger.info("Loaded plugin: %s (%s)", name, instance.category.value)

    def summary(self) -> str:
        """Return a human-readable summary of loaded and skipped plugins."""
        loaded = (
            len(self.data_sources)
            + len(self.tools)
            + len(self.deliveries)
            + sum(len(v) for v in self.hooks.values())
        )
        lines = [f"Plugins: {loaded} loaded, {len(self._failed)} skipped"]

        if self.data_sources:
            names = ", ".join(s.name for s in self.data_sources)
            lines.append(f"  Data sources: {names}")
        if self.tools:
            names = ", ".join(t.name for t in self.tools)
            lines.append(f"  Tools: {names}")
        if self.deliveries:
            names = ", ".join(d.name for d in self.deliveries)
            lines.append(f"  Delivery: {names}")
        for point, hooks in self.hooks.items():
            if hooks:
                names = ", ".join(h.name for h in hooks)
                lines.append(f"  Hooks ({point}): {names}")
        if self._failed:
            for name, reason in self._failed:
                lines.append(f"  Skipped {name}: {reason}")

        return "\n".join(lines)
