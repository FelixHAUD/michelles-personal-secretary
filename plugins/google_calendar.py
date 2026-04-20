"""Google Calendar DataSource plugin."""

from __future__ import annotations

import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from secretary.plugin import ConfigRequirement, DataSource

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = Path.home() / ".secretary" / "token.json"


class GoogleCalendarSource(DataSource):
    name = "google_calendar"
    description = "Fetches events from Google Calendar"
    config_schema = [
        ConfigRequirement(
            key="GOOGLE_CREDENTIALS_PATH",
            description="Path to Google OAuth credentials.json",
        ),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        self._credentials_path = config["GOOGLE_CREDENTIALS_PATH"]

    def fetch_events(self, start: datetime, end: datetime) -> list[dict]:
        creds = _get_credentials(self._credentials_path)
        service = build("calendar", "v3", credentials=creds)

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return [_normalize_event(item) for item in result.get("items", [])]


def _get_credentials(credentials_path: str) -> Credentials:
    """Get valid Google OAuth credentials, refreshing or running auth flow as needed."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
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


def _normalize_event(item: dict) -> dict:
    """Convert a Google Calendar API event into a normalized dict."""
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})

    return {
        "event_id": item.get("id", ""),
        "title": item.get("summary", "(No title)"),
        "start": _parse_datetime(start_raw).isoformat(),
        "end": _parse_datetime(end_raw).isoformat(),
        "location": item.get("location", ""),
        "description": item.get("description", ""),
        "source": "google_calendar",
    }


def _parse_datetime(dt_dict: dict) -> datetime:
    """Parse a Google Calendar datetime dict (handles both dateTime and date)."""
    if "dateTime" in dt_dict:
        return datetime.fromisoformat(dt_dict["dateTime"])
    elif "date" in dt_dict:
        return datetime.fromisoformat(dt_dict["date"]).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
