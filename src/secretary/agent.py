"""AI agent — sends events to Gemini, gets structured reminders back."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from google import genai
from google.genai import types

from .models import Conflict, Event, Reminder

SYSTEM_PROMPT = """\
You are a personal secretary AI. Your job is to analyze today's upcoming events \
and generate smart, actionable reminders.

## User Context
- Home address: {home_address}
- Current date/time: {current_time}

## Reminder Rules (apply ALL that match to each event)

1. PHYSICAL ADDRESS: If an event has a physical address, estimate a reasonable \
drive time from the user's home address. Add a 30-minute buffer. The reminder \
should tell them when to leave.

2. ZOOM / VIRTUAL MEETING: Remind 10 minutes before the event. Include the \
Zoom link or meeting URL if available in the event description or location.

3. CANVAS DEADLINE: If the event is an assignment deadline (from Canvas LMS), \
remind 24 hours before AND the morning of the due date.

4. FLIGHT: If the event appears to be a flight, remind the night before \
(include a packing checklist) AND 2.5 hours before departure.

5. EARLY MORNING (before 9 AM): Include a note to "Set an alarm for [time]" \
in the reminder.

6. SCHEDULING CONFLICTS: If two events overlap in time and there is not enough \
travel time between them (especially if both have physical locations), flag \
this as a conflict.

## Output Format

Respond with ONLY a JSON object (no markdown, no explanation) with this structure:

{{
  "reminders": [
    {{
      "event_id": "string",
      "event_title": "string",
      "remind_at": "ISO 8601 datetime string",
      "message": "The reminder text to show the user",
      "priority": "high" | "normal" | "low"
    }}
  ],
  "conflicts": [
    {{
      "event_ids": ["id1", "id2"],
      "description": "Description of the conflict"
    }}
  ]
}}

If there are no events, return {{"reminders": [], "conflicts": []}}.
Generate multiple reminders per event if the rules call for it (e.g. Canvas gets two).\
"""


def _format_events(events: list[Event]) -> str:
    """Format all events into a readable text block for the prompt."""
    if not events:
        return "No upcoming events found."

    lines = [f"Here are the upcoming events ({len(events)} total):\n"]
    for i, event in enumerate(events, 1):
        lines.append(f"--- Event {i} ---")
        lines.append(f"ID: {event.event_id}")
        lines.append(f"Title: {event.title}")
        lines.append(f"Start: {event.start.isoformat()}")
        lines.append(f"End: {event.end.isoformat()}")
        if event.location:
            lines.append(f"Location: {event.location}")
        if event.description:
            # Truncate very long descriptions
            desc = event.description[:500]
            lines.append(f"Description: {desc}")
        lines.append(f"Source: {event.source}")
        lines.append("")

    return "\n".join(lines)


def generate_reminders(
    events: list[Event],
    api_key: str,
    home_address: str,
) -> tuple[list[Reminder], list[Conflict]]:
    """Send all events to Gemini in one call, get structured reminders back.

    Args:
        events: All upcoming events from all sources.
        api_key: Gemini API key.
        home_address: User's home address for travel context.

    Returns:
        Tuple of (reminders, conflicts).
    """
    client = genai.Client(api_key=api_key)

    now = datetime.now(timezone.utc)
    system = SYSTEM_PROMPT.format(
        home_address=home_address or "Not provided",
        current_time=now.isoformat(),
    )

    user_message = _format_events(events)

    # Try primary model, fall back if overloaded
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    last_error = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=8192,
                    temperature=0.3,
                ),
            )
            return _parse_response(response.text)
        except Exception as e:
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"  {model} is overloaded, trying next model...")
                continue
            raise

    raise last_error


def _parse_response(text: str) -> tuple[list[Reminder], list[Conflict]]:
    """Parse the model's JSON response into Reminder and Conflict objects."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines[1:] if not l.strip() == "```"]
        cleaned = "\n".join(lines)

    data = json.loads(cleaned)

    reminders = []
    for r in data.get("reminders", []):
        reminders.append(
            Reminder(
                event_id=r["event_id"],
                event_title=r["event_title"],
                remind_at=datetime.fromisoformat(r["remind_at"]),
                message=r["message"],
                priority=r.get("priority", "normal"),
            )
        )

    conflicts = []
    for c in data.get("conflicts", []):
        conflicts.append(
            Conflict(
                event_ids=c["event_ids"],
                description=c["description"],
            )
        )

    return reminders, conflicts
