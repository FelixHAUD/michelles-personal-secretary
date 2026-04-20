"""Google Calendar event fetching."""

from __future__ import annotations

import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .models import Event

# Read-only scope — we never modify calendar data
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TOKEN_PATH = Path.home() / ".secretary" / "token.json"


def _get_credentials(credentials_path: str) -> Credentials:
    """Get valid Google OAuth credentials, refreshing or running auth flow as needed."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Try to use Chrome for the OAuth flow instead of system default
        try:
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            webbrowser.register(
                "chrome", None,
                webbrowser.BackgroundBrowser(chrome_path),
                preferred=True,
            )
        except Exception:
            pass  # Fall back to default browser
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)

    # Save token for next run
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    return creds


def fetch_events(
    credentials_path: str,
    lookahead_hours: int = 48,
) -> list[Event]:
    """Fetch upcoming events from Google Calendar.

    Args:
        credentials_path: Path to Google OAuth credentials.json file.
        lookahead_hours: How many hours ahead to look for events.

    Returns:
        List of normalized Event objects.
    """
    creds = _get_credentials(credentials_path)
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(hours=lookahead_hours)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [_normalize_event(item) for item in result.get("items", [])]


def _normalize_event(item: dict) -> Event:
    """Convert a Google Calendar API event into our Event model."""
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})

    start = _parse_datetime(start_raw)
    end = _parse_datetime(end_raw)

    return Event(
        event_id=item.get("id", ""),
        title=item.get("summary", "(No title)"),
        start=start,
        end=end,
        location=item.get("location", ""),
        description=item.get("description", ""),
        source="google_calendar",
        raw=item,
    )


def _parse_datetime(dt_dict: dict) -> datetime:
    """Parse a Google Calendar datetime dict (handles both dateTime and date)."""
    if "dateTime" in dt_dict:
        return datetime.fromisoformat(dt_dict["dateTime"])
    elif "date" in dt_dict:
        # All-day event — treat as midnight
        return datetime.fromisoformat(dt_dict["date"]).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
