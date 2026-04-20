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
    lookahead_hours: int = 6


@dataclass
class SecretaryConfig:
    user: UserConfig = field(default_factory=UserConfig)
    gemini_api_key: str = ""
    google_credentials_path: str = "credentials.json"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    google_maps_api_key: str = ""
    canvas_api_token: str = ""
    canvas_base_url: str = ""
    env: dict[str, str] = field(default_factory=dict)

    def merged_env(self) -> dict[str, str]:
        """Return env dict with top-level config keys included for plugin config checks."""
        merged = dict(self.env)
        if self.google_credentials_path:
            merged["GOOGLE_CREDENTIALS_PATH"] = self.google_credentials_path
        if self.gemini_api_key:
            merged["GEMINI_API_KEY"] = self.gemini_api_key
        if self.twilio_account_sid:
            merged["TWILIO_ACCOUNT_SID"] = self.twilio_account_sid
        if self.twilio_auth_token:
            merged["TWILIO_AUTH_TOKEN"] = self.twilio_auth_token
        if self.twilio_from_number:
            merged["TWILIO_FROM_NUMBER"] = self.twilio_from_number
        if self.sendgrid_api_key:
            merged["SENDGRID_API_KEY"] = self.sendgrid_api_key
        if self.sendgrid_from_email:
            merged["SENDGRID_FROM_EMAIL"] = self.sendgrid_from_email
        if self.google_maps_api_key:
            merged["GOOGLE_MAPS_API_KEY"] = self.google_maps_api_key
        if self.canvas_api_token:
            merged["CANVAS_API_TOKEN"] = self.canvas_api_token
        if self.canvas_base_url:
            merged["CANVAS_BASE_URL"] = self.canvas_base_url
        return merged
