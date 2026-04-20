"""Plugin system — drop a .py file in plugins/ and it auto-registers."""

from .base import (
    BasePlugin,
    ConfigRequirement,
    DataSource,
    Delivery,
    Hook,
    PluginCategory,
    Tool,
)
from .loader import discover_plugins
from .registry import PluginRegistry

__all__ = [
    "BasePlugin",
    "ConfigRequirement",
    "DataSource",
    "Delivery",
    "Hook",
    "PluginCategory",
    "Tool",
    "PluginRegistry",
    "discover_plugins",
]
