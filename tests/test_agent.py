"""Tests for the AI agent — prompt construction and response parsing."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from secretary.agent import Event, format_events, generate_reminders
from secretary.agent.loop import _parse_response


class TestFormatEvents:
    def test_formats_multiple_events(self, sample_events):
        result = format_events(sample_events)

        assert "3 total" in result
        assert "Team Standup" in result
        assert "Dentist Appointment" in result
        assert "Early Gym Session" in result
        assert "evt_001" in result
        assert "456 Oak Ave" in result

    def test_formats_empty_list(self):
        result = format_events([])
        assert "No upcoming events" in result

    def test_truncates_long_descriptions(self):
        event = Event(
            event_id="long",
            title="Wordy Event",
            start=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 21, 11, 0, tzinfo=timezone.utc),
            description="x" * 1000,
            source="test",
        )
        result = format_events([event])
        assert len(result) < 1000


class TestParseResponse:
    def test_parses_valid_json(self, mock_agent_json_response):
        output = _parse_response(mock_agent_json_response)

        assert len(output.reminders) == 3
        assert output.reminders[0].event_id == "evt_001"
        assert output.reminders[0].event_title == "Team Standup"
        assert "zoom.us" in output.reminders[0].message
        assert output.reminders[1].priority == "high"
        assert output.reminders[2].remind_at.hour == 5
        assert output.conflicts == []

    def test_parses_json_wrapped_in_code_fences(self):
        wrapped = '```json\n{"reminders": [], "conflicts": []}\n```'
        output = _parse_response(wrapped)
        assert output.reminders == []
        assert output.conflicts == []

    def test_parses_conflicts(self):
        response = '''{
            "reminders": [],
            "conflicts": [
                {
                    "event_ids": ["evt_001", "evt_002"],
                    "description": "Team Standup and Dentist overlap with no travel gap"
                }
            ]
        }'''
        output = _parse_response(response)
        assert len(output.conflicts) == 1
        assert "evt_001" in output.conflicts[0].event_ids
        assert "overlap" in output.conflicts[0].description

    def test_handles_missing_optional_fields(self):
        response = '''{
            "reminders": [
                {
                    "event_id": "evt_001",
                    "event_title": "Test",
                    "remind_at": "2026-04-21T08:00:00+00:00",
                    "message": "Reminder"
                }
            ],
            "conflicts": []
        }'''
        output = _parse_response(response)
        assert output.reminders[0].priority == "normal"


class TestGenerateReminders:
    @patch("secretary.agent.loop.genai.Client")
    def test_sends_all_events_in_single_call(self, mock_client_cls, sample_events):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '{"reminders": [], "conflicts": []}'
        mock_client.models.generate_content.return_value = mock_response

        output = generate_reminders(
            events=sample_events,
            api_key="fake-key",
            home_address="123 Main St",
        )

        # Verify single API call
        mock_client.models.generate_content.assert_called_once()

        # Verify all events are in the prompt
        call_args = mock_client.models.generate_content.call_args
        user_message = call_args.kwargs["contents"]
        assert "Team Standup" in user_message
        assert "Dentist Appointment" in user_message
        assert "Early Gym Session" in user_message

        # Verify system prompt includes home address
        config = call_args.kwargs["config"]
        assert "123 Main St" in config.system_instruction

    @patch("secretary.agent.loop.genai.Client")
    def test_uses_correct_model(self, mock_client_cls, sample_events):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '{"reminders": [], "conflicts": []}'
        mock_client.models.generate_content.return_value = mock_response

        generate_reminders(sample_events, "fake-key", "home")

        call_args = mock_client.models.generate_content.call_args
        assert call_args.kwargs["model"] == "gemini-2.5-flash"
