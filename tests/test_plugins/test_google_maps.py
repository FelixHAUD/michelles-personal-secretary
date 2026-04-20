"""Tests for Google Maps Tool plugin."""

import sys
from unittest.mock import MagicMock

import pytest

from secretary.plugin import PluginRegistry

# ---------------------------------------------------------------------------
# Stub out the googlemaps SDK so tests run without it installed.
# ---------------------------------------------------------------------------
_googlemaps = MagicMock()
sys.modules.setdefault("googlemaps", _googlemaps)

from plugins.google_maps import GoogleMapsTool  # noqa: E402


class TestGetToolDefinition:
    def test_returns_correct_schema(self):
        plugin = GoogleMapsTool()
        _googlemaps.Client.return_value = MagicMock()
        plugin.initialize({"GOOGLE_MAPS_API_KEY": "fake-key"})

        defn = plugin.get_tool_definition()

        assert defn["name"] == "get_drive_time"
        assert "drive time" in defn["description"].lower()
        schema = defn["input_schema"]
        assert schema["type"] == "object"
        assert "destination" in schema["properties"]
        assert "origin" in schema["properties"]
        assert schema["required"] == ["destination"]


class TestExecute:
    def _make_plugin(self, home_address="123 Main St"):
        mock_client = MagicMock()
        _googlemaps.Client.return_value = mock_client

        plugin = GoogleMapsTool()
        config = {"GOOGLE_MAPS_API_KEY": "fake-key"}
        if home_address:
            config["HOME_ADDRESS"] = home_address
        plugin.initialize(config)
        return plugin, mock_client

    def test_returns_formatted_drive_time(self):
        plugin, mock_client = self._make_plugin()
        mock_client.directions.return_value = [
            {
                "legs": [
                    {
                        "duration": {"text": "25 mins"},
                        "distance": {"text": "12.3 mi"},
                    }
                ]
            }
        ]

        result = plugin.execute({"destination": "456 Oak Ave"})

        assert result == "Drive time: 25 mins (12.3 mi)"
        mock_client.directions.assert_called_once_with(
            "123 Main St", "456 Oak Ave", mode="driving"
        )

    def test_uses_explicit_origin_over_home(self):
        plugin, mock_client = self._make_plugin()
        mock_client.directions.return_value = [
            {
                "legs": [
                    {
                        "duration": {"text": "10 mins"},
                        "distance": {"text": "3.1 mi"},
                    }
                ]
            }
        ]

        result = plugin.execute(
            {"origin": "789 Pine St", "destination": "456 Oak Ave"}
        )

        mock_client.directions.assert_called_once_with(
            "789 Pine St", "456 Oak Ave", mode="driving"
        )

    def test_falls_back_to_home_address_when_origin_missing(self):
        plugin, mock_client = self._make_plugin(home_address="Home Sweet Home")
        mock_client.directions.return_value = [
            {
                "legs": [
                    {
                        "duration": {"text": "15 mins"},
                        "distance": {"text": "5.0 mi"},
                    }
                ]
            }
        ]

        result = plugin.execute({"destination": "456 Oak Ave"})

        mock_client.directions.assert_called_once_with(
            "Home Sweet Home", "456 Oak Ave", mode="driving"
        )

    def test_error_when_no_origin_and_no_home(self):
        plugin, mock_client = self._make_plugin(home_address="")

        result = plugin.execute({"destination": "456 Oak Ave"})

        assert "no origin address" in result.lower() or "no home address" in result.lower()
        mock_client.directions.assert_not_called()

    def test_no_route_found(self):
        plugin, mock_client = self._make_plugin()
        mock_client.directions.return_value = []

        result = plugin.execute({"destination": "Middle of Nowhere"})

        assert "no route found" in result.lower()

    def test_handles_api_error_gracefully(self):
        plugin, mock_client = self._make_plugin()
        mock_client.directions.side_effect = Exception("API quota exceeded")

        result = plugin.execute({"destination": "456 Oak Ave"})

        assert "error" in result.lower()
        assert "API quota exceeded" in result


class TestRegistrySkipsMissingConfig:
    def test_missing_api_key_causes_skip(self):
        registry = PluginRegistry()
        registry.register(GoogleMapsTool, {})

        assert len(registry.tools) == 0
        assert len(registry._failed) == 1
        assert "Missing config" in registry._failed[0][1]
