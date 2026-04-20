"""Tests for Google Calendar event fetching and normalization."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from secretary.calendar import _normalize_event, _parse_datetime, fetch_events


class TestParseDateTime:
    def test_parses_datetime_with_timezone(self):
        result = _parse_datetime({"dateTime": "2026-04-21T09:00:00-05:00"})
        assert result.hour == 9
        assert result.year == 2026

    def test_parses_all_day_date(self):
        result = _parse_datetime({"date": "2026-04-22"})
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 22

    def test_handles_missing_fields(self):
        result = _parse_datetime({})
        assert isinstance(result, datetime)


class TestNormalizeEvent:
    def test_normalizes_standard_event(self):
        raw = {
            "id": "abc123",
            "summary": "Team Standup",
            "start": {"dateTime": "2026-04-21T09:00:00-05:00"},
            "end": {"dateTime": "2026-04-21T09:30:00-05:00"},
            "location": "https://zoom.us/j/123456789",
            "description": "Daily standup",
        }
        event = _normalize_event(raw)

        assert event.event_id == "abc123"
        assert event.title == "Team Standup"
        assert event.location == "https://zoom.us/j/123456789"
        assert event.description == "Daily standup"
        assert event.source == "google_calendar"
        assert event.raw == raw

    def test_handles_missing_summary(self):
        raw = {
            "id": "no_title",
            "start": {"dateTime": "2026-04-21T09:00:00-05:00"},
            "end": {"dateTime": "2026-04-21T09:30:00-05:00"},
        }
        event = _normalize_event(raw)
        assert event.title == "(No title)"

    def test_handles_all_day_event(self):
        raw = {
            "id": "all_day",
            "summary": "Holiday",
            "start": {"date": "2026-04-22"},
            "end": {"date": "2026-04-23"},
        }
        event = _normalize_event(raw)
        assert event.start.day == 22
        assert event.end.day == 23


class TestFetchEvents:
    @patch("secretary.calendar.build")
    @patch("secretary.calendar._get_credentials")
    def test_fetch_returns_normalized_events(
        self, mock_creds, mock_build, mock_calendar_response
    ):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events().list().execute.return_value = mock_calendar_response

        events = fetch_events("fake_creds.json")

        assert len(events) == 3
        assert events[0].event_id == "abc123"
        assert events[0].title == "Team Standup"
        assert events[1].location == "456 Oak Ave, Springfield, IL 62701"
        assert events[2].title == "All Day Event"

    @patch("secretary.calendar.build")
    @patch("secretary.calendar._get_credentials")
    def test_fetch_handles_empty_calendar(self, mock_creds, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events().list().execute.return_value = {"items": []}

        events = fetch_events("fake_creds.json")
        assert events == []
