"""Configuration package."""

from .loader import load_config
from .schema import SecretaryConfig, UserConfig

__all__ = ["SecretaryConfig", "UserConfig", "load_config"]
