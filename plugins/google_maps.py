"""Google Maps Tool plugin — drive time lookups."""

from __future__ import annotations

from typing import Any

from secretary.plugin import ConfigRequirement, Tool


class GoogleMapsTool(Tool):
    name = "google_maps"
    description = "Look up drive time between two addresses using Google Maps"
    config_schema = [
        ConfigRequirement(
            key="GOOGLE_MAPS_API_KEY",
            description="Google Maps Directions API key",
            secret=True,
        ),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        import googlemaps

        self._client = googlemaps.Client(key=config["GOOGLE_MAPS_API_KEY"])
        self._home_address = config.get("HOME_ADDRESS", "")

    def get_tool_definition(self) -> dict:
        return {
            "name": "get_drive_time",
            "description": (
                "Get the estimated drive time in minutes between an origin "
                "and destination address. Use this when an event has a "
                "physical address to determine when the user should leave."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Starting address (default: user's home)",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination address",
                    },
                },
                "required": ["destination"],
            },
        }

    def execute(self, tool_input: dict) -> str:
        origin = tool_input.get("origin") or self._home_address
        destination = tool_input["destination"]

        if not origin:
            return "Error: No origin address provided and no home address configured"

        try:
            result = self._client.directions(origin, destination, mode="driving")
            if result:
                leg = result[0]["legs"][0]
                duration = leg["duration"]["text"]
                distance = leg["distance"]["text"]
                return f"Drive time: {duration} ({distance})"
            return "Could not determine drive time — no route found"
        except Exception as e:
            return f"Error looking up drive time: {e}"
