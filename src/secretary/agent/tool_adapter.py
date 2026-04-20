"""Convert plugin Tool objects into Gemini function declarations.

This module bridges the plugin system and the AI agent. It converts Tool
plugins into Gemini-compatible function declarations and builds a dispatch
map for routing tool calls back to the right plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.genai import types

if TYPE_CHECKING:
    from secretary.plugin import PluginRegistry
    from secretary.plugin.base import Tool


def build_gemini_tools(registry: PluginRegistry) -> list[types.Tool] | None:
    """Convert registered Tool plugins into Gemini function declarations."""
    if not registry.tools:
        return None

    declarations = []
    for tool_plugin in registry.tools:
        defn = tool_plugin.get_tool_definition()
        declarations.append(types.FunctionDeclaration(
            name=defn["name"],
            description=defn["description"],
            parameters=defn.get("input_schema"),
        ))
    return [types.Tool(function_declarations=declarations)]


def build_tool_dispatch(registry: PluginRegistry) -> dict[str, Tool]:
    """Map tool name -> Tool plugin instance for execution routing."""
    dispatch = {}
    for tool_plugin in registry.tools:
        defn = tool_plugin.get_tool_definition()
        dispatch[defn["name"]] = tool_plugin
    return dispatch
