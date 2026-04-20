"""Minimal config: load .env and expose settings."""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_config() -> dict[str, str]:
    """Load environment variables from .env file and return config dict."""
    # Look for .env in the project root (two levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path)

    return {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "google_credentials_path": os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
        "home_address": os.environ.get("HOME_ADDRESS", ""),
    }
