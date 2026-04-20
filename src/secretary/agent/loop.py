"""AI agent loop — sends events to Gemini, parses structured reminders back."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types

from .prompt import build_system_prompt
from .types import AgentOutput, Conflict, Event, Reminder

logger = logging.getLogger(__name__)


def format_events(events: list[Event]) -> str:
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
            desc = event.description[:500]
            lines.append(f"Description: {desc}")
        lines.append(f"Source: {event.source}")
        lines.append("")

    return "\n".join(lines)


def generate_reminders(
    events: list[Event],
    api_key: str,
    home_address: str,
) -> AgentOutput:
    """Send all events to Gemini in one call, get structured reminders back."""
    client = genai.Client(api_key=api_key)

    now = datetime.now(timezone.utc)
    system = build_system_prompt(home_address, now.isoformat())
    user_message = format_events(events)

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
                    max_output_tokens=16384,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return _parse_response(response.text)
        except Exception as e:
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                logger.warning("%s is overloaded, trying next model...", model)
                continue
            raise

    raise last_error


def _parse_response(text: str) -> AgentOutput:
    """Parse the model's JSON response into an AgentOutput."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines[1:] if not l.strip() == "```"]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to salvage truncated JSON by closing open structures
        repaired = cleaned
        # Close any open strings, arrays, objects
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        if repaired.rstrip().endswith(","):
            repaired = repaired.rstrip()[:-1]
        # Close the string if truncated mid-string
        if repaired.count('"') % 2 == 1:
            repaired += '"'
        repaired += "]" * open_brackets + "}" * open_braces
        data = json.loads(repaired)

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

    return AgentOutput(reminders=reminders, conflicts=conflicts)
