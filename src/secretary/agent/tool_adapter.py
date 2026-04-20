"""Convert plugin Tool objects into Gemini function declarations.

This module bridges the plugin system and the AI agent. When we upgrade
to tool-use in Phase 2, this will convert Tool plugins into Gemini-compatible
function declarations and dispatch tool calls back to the right plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from secretary.plugin import PluginRegistry
    from secretary.plugin.base import Tool


def build_tool_definitions(registry: PluginRegistry) -> list[dict]:
    """Convert all registered Tool plugins into Gemini function declarations."""
    definitions = []
    for tool_plugin in registry.tools:
        defn = tool_plugin.get_tool_definition()
        definitions.append(defn)
    return definitions


def build_tool_dispatch(registry: PluginRegistry) -> dict[str, Tool]:
    """Map tool name -> Tool plugin instance for execution routing."""
    dispatch = {}
    for tool_plugin in registry.tools:
        defn = tool_plugin.get_tool_definition()
        dispatch[defn["name"]] = tool_plugin
    return dispatch
