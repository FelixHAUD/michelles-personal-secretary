"""Google Calendar DataSource plugin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build

from secretary.plugin import ConfigRequirement, DataSource
from secretary.util.google_auth import get_credentials


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
        creds = get_credentials(self._credentials_path)
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
