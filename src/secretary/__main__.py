"""Entry point: python -m secretary"""

import sys

from .agent import generate_reminders
from .calendar import fetch_events
from .config import load_config


def main():
    config = load_config()

    # Validate required config
    if not config["gemini_api_key"]:
        print("Error: GEMINI_API_KEY not set. Copy .env.example to .env and fill it in.")
        print("Get a free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Step 1: Fetch events
    print("Fetching Google Calendar events...")
    try:
        events = fetch_events(config["google_credentials_path"])
    except FileNotFoundError:
        print(
            f"Error: Google credentials not found at '{config['google_credentials_path']}'.\n"
            "Download credentials.json from Google Cloud Console and place it in the project root.\n"
            "See: https://developers.google.com/calendar/api/quickstart/python"
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        sys.exit(1)

    print(f"Found {len(events)} upcoming events.\n")

    if not events:
        print("No events in the next 48 hours. Nothing to do.")
        return

    # Step 2: Show what we fetched
    for event in events:
        loc = f" @ {event.location}" if event.location else ""
        print(f"  - {event.title}{loc}")
        print(f"    {event.start.strftime('%a %b %d, %I:%M %p')} - {event.end.strftime('%I:%M %p')}")
    print()

    # Step 3: Send to Gemini
    print("Analyzing events with Gemini...")
    reminders, conflicts = generate_reminders(
        events=events,
        api_key=config["gemini_api_key"],
        home_address=config["home_address"],
    )

    # Step 4: Print results
    if reminders:
        print(f"\n{'='*60}")
        print(f"  REMINDERS ({len(reminders)})")
        print(f"{'='*60}\n")
        for r in sorted(reminders, key=lambda x: x.remind_at):
            priority_marker = "!" if r.priority == "high" else " "
            print(f"  [{priority_marker}] {r.event_title}")
            print(f"      When: {r.remind_at.strftime('%a %b %d, %I:%M %p')}")
            print(f"      {r.message}")
            print()

    if conflicts:
        print(f"{'='*60}")
        print(f"  CONFLICTS ({len(conflicts)})")
        print(f"{'='*60}\n")
        for c in conflicts:
            print(f"  !! {c.description}")
            print()

    if not reminders and not conflicts:
        print("\nNo reminders or conflicts to report.")


if __name__ == "__main__":
    main()
