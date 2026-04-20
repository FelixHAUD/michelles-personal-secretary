"""Configuration schema."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserConfig:
    home_address: str = ""
    phone_number: str = ""
    email: str = ""
    timezone: str = "America/Los_Angeles"
    schedule_cron: str = "0 6 * * *"
    lookahead_hours: int = 48


@dataclass
class SecretaryConfig:
    user: UserConfig = field(default_factory=UserConfig)
    gemini_api_key: str = ""
    google_credentials_path: str = "credentials.json"
    env: dict[str, str] = field(default_factory=dict)

    def merged_env(self) -> dict[str, str]:
        """Return env dict with top-level config keys included for plugin config checks."""
        merged = dict(self.env)
        if self.google_credentials_path:
            merged["GOOGLE_CREDENTIALS_PATH"] = self.google_credentials_path
        if self.gemini_api_key:
            merged["GEMINI_API_KEY"] = self.gemini_api_key
        return merged
