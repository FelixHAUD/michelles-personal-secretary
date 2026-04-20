"""Base classes for the plugin system.

Four plugin categories:
- DataSource: fetches events from external services
- Tool: provides tools the AI agent can call
- Delivery: sends reminders to the user
- Hook: transforms data at pre_agent or post_agent points
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class PluginCategory(Enum):
    DATA_SOURCE = "data_source"
    TOOL = "tool"
    DELIVERY = "delivery"
    HOOK = "hook"


@dataclass
class ConfigRequirement:
    """One configuration key a plugin needs."""

    key: str
    description: str
    secret: bool = False
    required: bool = True


class BasePlugin(ABC):
    """All plugins inherit from this."""

    name: str = ""
    description: str = ""
    category: PluginCategory = PluginCategory.DATA_SOURCE
    config_schema: list[ConfigRequirement] = []

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Called once after config validation. Set up API clients here."""
        ...

    def shutdown(self) -> None:
        """Optional cleanup."""
        pass


class DataSource(BasePlugin):
    """Fetches events from an external service."""

    category = PluginCategory.DATA_SOURCE

    @abstractmethod
    def fetch_events(self, start: datetime, end: datetime) -> list[dict]:
        """Return normalized event dicts for the given time window."""
        ...


class Tool(BasePlugin):
    """Provides a tool the AI agent can call during reasoning."""

    category = PluginCategory.TOOL

    @abstractmethod
    def get_tool_definition(self) -> dict:
        """Return tool definition dict with name, description, input_schema."""
        ...

    @abstractmethod
    def execute(self, tool_input: dict) -> str:
        """Run the tool with the given input, return result string."""
        ...


class Delivery(BasePlugin):
    """Sends reminders to the user via a channel (SMS, email, etc.)."""

    category = PluginCategory.DELIVERY

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str) -> bool:
        """Send a reminder. Return True on success."""
        ...


class Hook(BasePlugin):
    """Transforms data flowing through the pipeline."""

    category = PluginCategory.HOOK
    hook_point: str = "pre_agent"  # "pre_agent" or "post_agent"

    @abstractmethod
    def process(self, data: Any) -> Any:
        """Transform data at this hook point."""
        ...
