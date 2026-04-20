"""Tests for the AI agent — prompt construction, response parsing, and tool-use loop."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from secretary.agent import Event, format_events, generate_reminders
from secretary.agent.loop import _parse_response
from secretary.agent.tool_adapter import build_gemini_tools, build_tool_dispatch


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

    @patch("secretary.agent.loop.genai.Client")
    def test_no_tools_when_registry_is_none(self, mock_client_cls, sample_events):
        """When registry is None, no tools parameter is sent (single-call path)."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '{"reminders": [], "conflicts": []}'
        mock_client.models.generate_content.return_value = mock_response

        generate_reminders(sample_events, "fake-key", "home", registry=None)

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs["config"]
        # Single-call path does not set tools in the config
        assert not hasattr(config, "tools") or config.tools is None

    @patch("secretary.agent.loop.genai.Client")
    def test_no_tools_when_registry_has_no_tools(self, mock_client_cls, sample_events):
        """When registry exists but has no tool plugins, single-call path is used."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '{"reminders": [], "conflicts": []}'
        mock_client.models.generate_content.return_value = mock_response

        registry = MagicMock()
        registry.tools = []

        generate_reminders(sample_events, "fake-key", "home", registry=registry)

        # Should use the single-call path (contents is a string, not a list)
        call_args = mock_client.models.generate_content.call_args
        assert isinstance(call_args.kwargs["contents"], str)


class TestBuildGeminiTools:
    def test_returns_none_when_no_tools(self):
        registry = MagicMock()
        registry.tools = []
        assert build_gemini_tools(registry) is None

    @patch("secretary.agent.tool_adapter.types")
    def test_converts_tools_to_declarations(self, mock_types):
        tool_plugin = MagicMock()
        tool_plugin.get_tool_definition.return_value = {
            "name": "get_drive_time",
            "description": "Get driving time between two addresses",
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["origin", "destination"],
            },
        }

        registry = MagicMock()
        registry.tools = [tool_plugin]

        build_gemini_tools(registry)

        mock_types.FunctionDeclaration.assert_called_once_with(
            name="get_drive_time",
            description="Get driving time between two addresses",
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["origin", "destination"],
            },
        )
        mock_types.Tool.assert_called_once()

    @patch("secretary.agent.tool_adapter.types")
    def test_handles_tool_without_input_schema(self, mock_types):
        tool_plugin = MagicMock()
        tool_plugin.get_tool_definition.return_value = {
            "name": "get_current_time",
            "description": "Get current UTC time",
        }

        registry = MagicMock()
        registry.tools = [tool_plugin]

        build_gemini_tools(registry)

        mock_types.FunctionDeclaration.assert_called_once_with(
            name="get_current_time",
            description="Get current UTC time",
            parameters=None,
        )


class TestBuildToolDispatch:
    def test_maps_names_to_plugins(self):
        tool_a = MagicMock()
        tool_a.get_tool_definition.return_value = {"name": "tool_a"}
        tool_b = MagicMock()
        tool_b.get_tool_definition.return_value = {"name": "tool_b"}

        registry = MagicMock()
        registry.tools = [tool_a, tool_b]

        dispatch = build_tool_dispatch(registry)

        assert dispatch["tool_a"] is tool_a
        assert dispatch["tool_b"] is tool_b
        assert len(dispatch) == 2


class TestToolUseLoop:
    """Test the full tool-use round trip through generate_reminders."""

    @patch("secretary.agent.loop.genai.Client")
    def test_tool_call_round_trip(self, mock_client_cls, sample_events):
        """Gemini returns a function_call, tool executes, result sent back, final JSON parsed."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Build a mock tool plugin
        tool_plugin = MagicMock()
        tool_plugin.get_tool_definition.return_value = {
            "name": "get_drive_time",
            "description": "Get driving time",
            "input_schema": {
                "type": "object",
                "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}},
            },
        }
        tool_plugin.execute.return_value = "35 minutes"

        registry = MagicMock()
        registry.tools = [tool_plugin]

        # First response: Gemini makes a function call
        func_call_part = MagicMock()
        func_call_part.function_call = MagicMock()
        func_call_part.function_call.name = "get_drive_time"
        func_call_part.function_call.args = {"origin": "123 Main St", "destination": "456 Oak Ave"}

        first_response = MagicMock()
        first_response.candidates = [MagicMock()]
        first_response.candidates[0].content = MagicMock()
        first_response.candidates[0].content.parts = [func_call_part]

        # Second response: Gemini returns final JSON
        text_part = MagicMock()
        text_part.function_call = None

        second_response = MagicMock()
        second_response.candidates = [MagicMock()]
        second_response.candidates[0].content = MagicMock()
        second_response.candidates[0].content.parts = [text_part]
        second_response.text = '{"reminders": [{"event_id": "evt_002", "event_title": "Dentist Appointment", "remind_at": "2026-04-21T12:45:00+00:00", "message": "Leave now, 35 min drive", "priority": "high"}], "conflicts": []}'

        mock_client.models.generate_content.side_effect = [first_response, second_response]

        output = generate_reminders(
            events=sample_events,
            api_key="fake-key",
            home_address="123 Main St",
            registry=registry,
        )

        # Verify tool was executed with correct args
        tool_plugin.execute.assert_called_once_with(
            {"origin": "123 Main St", "destination": "456 Oak Ave"}
        )

        # Verify two API calls were made (initial + after tool response)
        assert mock_client.models.generate_content.call_count == 2

        # Verify the second call includes the function response in contents
        second_call_args = mock_client.models.generate_content.call_args_list[1]
        contents = second_call_args.kwargs["contents"]
        # contents should be: [user msg, assistant response, function response]
        assert len(contents) == 3

        # Verify final output is parsed correctly
        assert len(output.reminders) == 1
        assert output.reminders[0].event_title == "Dentist Appointment"
        assert "35 min" in output.reminders[0].message

    @patch("secretary.agent.loop.genai.Client")
    def test_tool_error_is_isolated(self, mock_client_cls, sample_events):
        """If a tool raises an exception, the error is sent back to Gemini as the result."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        tool_plugin = MagicMock()
        tool_plugin.get_tool_definition.return_value = {
            "name": "get_drive_time",
            "description": "Get driving time",
            "input_schema": {"type": "object", "properties": {}},
        }
        tool_plugin.execute.side_effect = RuntimeError("API timeout")

        registry = MagicMock()
        registry.tools = [tool_plugin]

        # First response: function call
        func_call_part = MagicMock()
        func_call_part.function_call = MagicMock()
        func_call_part.function_call.name = "get_drive_time"
        func_call_part.function_call.args = {}

        first_response = MagicMock()
        first_response.candidates = [MagicMock()]
        first_response.candidates[0].content = MagicMock()
        first_response.candidates[0].content.parts = [func_call_part]

        # Second response: final JSON (model handles the error gracefully)
        text_part = MagicMock()
        text_part.function_call = None
        second_response = MagicMock()
        second_response.candidates = [MagicMock()]
        second_response.candidates[0].content = MagicMock()
        second_response.candidates[0].content.parts = [text_part]
        second_response.text = '{"reminders": [], "conflicts": []}'

        mock_client.models.generate_content.side_effect = [first_response, second_response]

        # Should not raise — error is isolated
        output = generate_reminders(
            events=sample_events,
            api_key="fake-key",
            home_address="home",
            registry=registry,
        )

        assert output.reminders == []
        assert mock_client.models.generate_content.call_count == 2

    @patch("secretary.agent.loop.genai.Client")
    def test_multiple_tool_calls_in_one_response(self, mock_client_cls, sample_events):
        """Gemini can return multiple function calls in a single response."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        tool_a = MagicMock()
        tool_a.get_tool_definition.return_value = {
            "name": "tool_a", "description": "A", "input_schema": {"type": "object", "properties": {}},
        }
        tool_a.execute.return_value = "result_a"

        tool_b = MagicMock()
        tool_b.get_tool_definition.return_value = {
            "name": "tool_b", "description": "B", "input_schema": {"type": "object", "properties": {}},
        }
        tool_b.execute.return_value = "result_b"

        registry = MagicMock()
        registry.tools = [tool_a, tool_b]

        # First response: two function calls
        part_a = MagicMock()
        part_a.function_call = MagicMock()
        part_a.function_call.name = "tool_a"
        part_a.function_call.args = {}

        part_b = MagicMock()
        part_b.function_call = MagicMock()
        part_b.function_call.name = "tool_b"
        part_b.function_call.args = {}

        first_response = MagicMock()
        first_response.candidates = [MagicMock()]
        first_response.candidates[0].content = MagicMock()
        first_response.candidates[0].content.parts = [part_a, part_b]

        # Second response: final JSON
        text_part = MagicMock()
        text_part.function_call = None
        second_response = MagicMock()
        second_response.candidates = [MagicMock()]
        second_response.candidates[0].content = MagicMock()
        second_response.candidates[0].content.parts = [text_part]
        second_response.text = '{"reminders": [], "conflicts": []}'

        mock_client.models.generate_content.side_effect = [first_response, second_response]

        generate_reminders(sample_events, "fake-key", "home", registry=registry)

        # Both tools should have been executed
        tool_a.execute.assert_called_once()
        tool_b.execute.assert_called_once()

        # The function response content should have 2 parts
        second_call_contents = mock_client.models.generate_content.call_args_list[1].kwargs["contents"]
        func_response_content = second_call_contents[2]  # [user, assistant, func_responses]
        assert func_response_content.role == "user"

    @patch("secretary.agent.loop.genai.Client")
    def test_tools_passed_in_config(self, mock_client_cls, sample_events):
        """When registry has tools, they are passed to Gemini in the config."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        tool_plugin = MagicMock()
        tool_plugin.get_tool_definition.return_value = {
            "name": "get_drive_time",
            "description": "Get driving time",
            "input_schema": {"type": "object", "properties": {}},
        }

        registry = MagicMock()
        registry.tools = [tool_plugin]

        # Response with no function calls (immediate text)
        text_part = MagicMock()
        text_part.function_call = None
        response = MagicMock()
        response.candidates = [MagicMock()]
        response.candidates[0].content = MagicMock()
        response.candidates[0].content.parts = [text_part]
        response.text = '{"reminders": [], "conflicts": []}'

        mock_client.models.generate_content.return_value = response

        generate_reminders(sample_events, "fake-key", "home", registry=registry)

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs["config"]
        assert config.tools is not None
