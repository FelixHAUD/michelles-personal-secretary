"""Shared Google OAuth helper — single token with all required scopes."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

TOKEN_PATH = Path(
    os.environ.get("GOOGLE_TOKEN_PATH", str(Path.home() / ".secretary" / "token.json"))
)


def get_credentials(credentials_path: str) -> Credentials:
    """Get valid Google OAuth credentials, refreshing if needed.

    On Cloud Run the token is written from Secret Manager at startup.
    Locally, if the token is missing or has wrong scopes, the caller
    must trigger the interactive flow (see google_calendar plugin).
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist_token_to_secret_manager(creds)
    elif not creds or not creds.valid:
        # Interactive flow needed — handled by google_calendar plugin
        return _run_interactive_flow(credentials_path)

    # Always save locally so the file stays fresh
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    return creds


def _run_interactive_flow(credentials_path: str) -> Credentials:
    """Run the browser-based OAuth flow (local only)."""
    import webbrowser

    from google_auth_oauthlib.flow import InstalledAppFlow

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        webbrowser.register(
            "chrome", None,
            webbrowser.BackgroundBrowser(chrome_path),
            preferred=True,
        )
    except Exception:
        pass
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    return creds


def _persist_token_to_secret_manager(creds: Credentials) -> None:
    """Write the refreshed token back to Secret Manager (cloud only)."""
    secret_name = os.environ.get("GOOGLE_TOKEN_SECRET")
    if not secret_name:
        return
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        client.add_secret_version(
            parent=secret_name,
            payload=secretmanager.SecretPayload(data=creds.to_json().encode("utf-8")),
        )
        logger.info("Persisted refreshed OAuth token to Secret Manager")
    except Exception as e:
        logger.warning("Failed to persist token to Secret Manager: %s", e)
