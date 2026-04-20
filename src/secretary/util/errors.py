"""Custom exception hierarchy."""


class SecretaryError(Exception):
    """Base exception for all secretary errors."""


class ConfigError(SecretaryError):
    """Configuration is missing or invalid."""


class PluginError(SecretaryError):
    """A plugin failed to load or execute."""


class AgentError(SecretaryError):
    """The AI agent failed to produce a valid response."""
