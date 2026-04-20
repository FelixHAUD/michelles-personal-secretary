"""Shared test fixtures."""

from datetime import datetime, timezone

import pytest

from secretary.models import Event


@pytest.fixture
def sample_events():
    """A realistic set of test events covering different reminder rules."""
    return [
        Event(
            event_id="evt_001",
            title="Team Standup",
            start=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 21, 9, 30, tzinfo=timezone.utc),
            location="https://zoom.us/j/123456789",
            description="Daily standup. Zoom link: https://zoom.us/j/123456789",
            source="google_calendar",
        ),
        Event(
            event_id="evt_002",
            title="Dentist Appointment",
            start=datetime(2026, 4, 21, 14, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
            location="456 Oak Ave, Springfield, IL 62701",
            source="google_calendar",
        ),
        Event(
            event_id="evt_003",
            title="Early Gym Session",
            start=datetime(2026, 4, 21, 6, 30, tzinfo=timezone.utc),
            end=datetime(2026, 4, 21, 7, 30, tzinfo=timezone.utc),
            location="789 Fitness Blvd",
            source="google_calendar",
        ),
    ]


@pytest.fixture
def mock_calendar_response():
    """Raw Google Calendar API response for testing normalization."""
    return {
        "items": [
            {
                "id": "abc123",
                "summary": "Team Standup",
                "start": {"dateTime": "2026-04-21T09:00:00-05:00"},
                "end": {"dateTime": "2026-04-21T09:30:00-05:00"},
                "location": "https://zoom.us/j/123456789",
                "description": "Daily standup",
            },
            {
                "id": "def456",
                "summary": "Dentist",
                "start": {"dateTime": "2026-04-21T14:00:00-05:00"},
                "end": {"dateTime": "2026-04-21T15:00:00-05:00"},
                "location": "456 Oak Ave, Springfield, IL 62701",
            },
            {
                "id": "ghi789",
                "summary": "All Day Event",
                "start": {"date": "2026-04-22"},
                "end": {"date": "2026-04-23"},
            },
        ]
    }


@pytest.fixture
def mock_agent_json_response():
    """A valid JSON response from Claude for testing parsing."""
    return '''{
  "reminders": [
    {
      "event_id": "evt_001",
      "event_title": "Team Standup",
      "remind_at": "2026-04-21T08:50:00+00:00",
      "message": "Team Standup starts in 10 minutes. Join here: https://zoom.us/j/123456789",
      "priority": "normal"
    },
    {
      "event_id": "evt_002",
      "event_title": "Dentist Appointment",
      "remind_at": "2026-04-21T12:45:00+00:00",
      "message": "Leave for your dentist appointment at 456 Oak Ave. Estimated drive time ~35 min + 30 min buffer.",
      "priority": "high"
    },
    {
      "event_id": "evt_003",
      "event_title": "Early Gym Session",
      "remind_at": "2026-04-21T05:45:00+00:00",
      "message": "Early Gym Session at 6:30 AM. Set an alarm for 5:45 AM!",
      "priority": "normal"
    }
  ],
  "conflicts": []
}'''
