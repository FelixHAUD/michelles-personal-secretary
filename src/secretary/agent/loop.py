"""AI agent loop — sends events to Gemini, parses structured reminders back."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

from .prompt import build_system_prompt
from .tool_adapter import build_gemini_tools, build_tool_dispatch
from .types import AgentOutput, Conflict, Event, Reminder

if TYPE_CHECKING:
    from secretary.plugin import PluginRegistry

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 10


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
    registry: PluginRegistry | None = None,
    user_timezone: str = "America/Los_Angeles",
) -> AgentOutput:
    """Send all events to Gemini, optionally with tool-use, get structured reminders back."""
    client = genai.Client(api_key=api_key)

    # Use the user's local timezone so Gemini can compare times correctly
    # with event timestamps (which come from Google Calendar in local time).
    now = datetime.now(ZoneInfo(user_timezone))
    system = build_system_prompt(home_address, now.isoformat())
    user_message = format_events(events)

    # Build tool declarations and dispatch map if registry has tools
    gemini_tools = None
    dispatch = {}
    if registry is not None:
        gemini_tools = build_gemini_tools(registry)
        if gemini_tools is not None:
            dispatch = build_tool_dispatch(registry)

    # Try primary model, fall back if overloaded, retry on rate limit
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    last_error = None
    for model in models:
        for attempt in range(3):
            try:
                if gemini_tools is not None:
                    return _tool_use_loop(
                        client, model, system, user_message, gemini_tools, dispatch,
                    )
                else:
                    return _single_call(client, model, system, user_message)
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning("%s is overloaded, trying next model...", model)
                    break  # try next model
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = _parse_retry_delay(err_str)
                    logger.warning(
                        "%s rate limited (attempt %d/3), waiting %ds...",
                        model, attempt + 1, wait,
                    )
                    time.sleep(wait)
                    continue  # retry same model
                raise

    raise last_error


def _parse_retry_delay(err_str: str, max_delay: int = 30) -> int:
    """Extract retry delay from error message, default 60s, capped for Cloud Run."""
    match = re.search(r"retry in (\d+)", err_str, re.IGNORECASE)
    delay = int(match.group(1)) if match else 60
    return min(delay, max_delay)


def _single_call(
    client: genai.Client,
    model: str,
    system: str,
    user_message: str,
) -> AgentOutput:
    """Original single-call path with no tools."""
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


def _tool_use_loop(
    client: genai.Client,
    model: str,
    system: str,
    user_message: str,
    gemini_tools: list[types.Tool],
    dispatch: dict,
) -> AgentOutput:
    """Multi-turn loop that handles Gemini function calls."""
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_message)])]

    for _round in range(_MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=gemini_tools,
                max_output_tokens=16384,
                temperature=0.3,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        # Check if the response contains function calls
        function_calls = [
            part for part in response.candidates[0].content.parts
            if part.function_call
        ]

        if not function_calls:
            # No tool calls — extract text and parse as JSON
            return _parse_response(response.text)

        # Execute each function call and collect responses
        func_response_parts = []
        for part in function_calls:
            name = part.function_call.name
            args = dict(part.function_call.args)
            logger.info("Tool call: %s(%s)", name, args)

            try:
                tool_plugin = dispatch[name]
                result = tool_plugin.execute(args)
            except Exception as e:
                logger.error("Tool %s failed: %s", name, e)
                result = f"Error: {e}"

            func_response_parts.append(
                types.Part.from_function_response(
                    name=name,
                    response={"result": result},
                )
            )

        # Append assistant response and function results for next round
        contents.append(response.candidates[0].content)
        contents.append(types.Content(role="user", parts=func_response_parts))

    # If we exhaust rounds, try to parse whatever text we have
    logger.warning("Exhausted %d tool-use rounds, parsing last response", _MAX_TOOL_ROUNDS)
    return _parse_response(response.text)


def _parse_response(text: str | None) -> AgentOutput:
    """Parse the model's JSON response into an AgentOutput."""
    if not text or not text.strip():
        logger.warning("Empty response from model, returning no reminders")
        return AgentOutput(reminders=[], conflicts=[])
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
