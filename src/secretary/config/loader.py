"""Load configuration from .env file."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .schema import SecretaryConfig, UserConfig


def load_config() -> SecretaryConfig:
    """Load config from .env file and environment variables."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path)

    # Collect all env vars that plugins might need
    env = {}
    for key, val in os.environ.items():
        env[key] = val

    return SecretaryConfig(
        user=UserConfig(
            home_address=os.environ.get("HOME_ADDRESS", ""),
            phone_number=os.environ.get("PHONE_NUMBER", ""),
            email=os.environ.get("EMAIL", ""),
            timezone=os.environ.get("TIMEZONE", "America/Los_Angeles"),
            lookahead_hours=int(os.environ.get("LOOKAHEAD_HOURS", "48")),
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        google_credentials_path=os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
        env=env,
    )
