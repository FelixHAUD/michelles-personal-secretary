"""Interactive setup wizard for first-time configuration."""

from __future__ import annotations

import getpass
from pathlib import Path


def run_wizard() -> None:
    """Walk the user through configuring the secretary."""
    print("=" * 60)
    print("  Michelle's Personal Secretary — Setup Wizard")
    print("=" * 60)
    print()
    print("This wizard will help you configure your secretary.")
    print("Press Enter to keep the default value shown in [brackets].")
    print()

    env_lines: list[str] = []

    # Step 1: Core settings
    print("--- Core Settings ---")
    home = input("Home address (for travel time calculations): ").strip()
    if home:
        env_lines.append(f"HOME_ADDRESS={home}")

    phone = input("Phone number for SMS reminders (e.g. +15551234567) [skip]: ").strip()
    if phone:
        env_lines.append(f"PHONE_NUMBER={phone}")

    email = input("Email for email reminders [skip]: ").strip()
    if email:
        env_lines.append(f"EMAIL={email}")

    tz = input("Timezone [America/Los_Angeles]: ").strip() or "America/Los_Angeles"
    env_lines.append(f"TIMEZONE={tz}")

    cron = input("Daily schedule (cron format) [0 6 * * *]: ").strip() or "0 6 * * *"
    env_lines.append(f"SCHEDULE_CRON={cron}")
    print()

    # Step 2: Gemini AI (required)
    print("--- Gemini AI (required) ---")
    print("Get a free API key at: https://aistudio.google.com/apikey")
    gemini_key = getpass.getpass("Gemini API key: ").strip()
    if gemini_key:
        env_lines.append(f"GEMINI_API_KEY={gemini_key}")
    else:
        print("  Warning: Gemini API key is required for the secretary to work.")
    print()

    # Step 3: Google Calendar (required)
    print("--- Google Calendar (required) ---")
    print("Download credentials.json from Google Cloud Console.")
    print("See: https://developers.google.com/calendar/api/quickstart/python")
    creds_path = input("Path to credentials.json [credentials.json]: ").strip() or "credentials.json"
    env_lines.append(f"GOOGLE_CREDENTIALS_PATH={creds_path}")
    print()

    # Step 4: Optional integrations
    print("--- Optional Integrations ---")
    print("Press Enter to skip any you don't want to set up now.\n")

    # Google Maps
    if _ask_yes_no("Enable Google Maps for drive time lookups?"):
        maps_key = getpass.getpass("  Google Maps API key: ").strip()
        if maps_key:
            env_lines.append(f"GOOGLE_MAPS_API_KEY={maps_key}")
    print()

    # Twilio SMS
    if _ask_yes_no("Enable Twilio SMS delivery?"):
        sid = input("  Twilio Account SID: ").strip()
        token = getpass.getpass("  Twilio Auth Token: ").strip()
        from_num = input("  Twilio phone number (e.g. +15559876543): ").strip()
        if sid and token and from_num:
            env_lines.append(f"TWILIO_ACCOUNT_SID={sid}")
            env_lines.append(f"TWILIO_AUTH_TOKEN={token}")
            env_lines.append(f"TWILIO_FROM_NUMBER={from_num}")
    print()

    # SendGrid Email
    if _ask_yes_no("Enable SendGrid email delivery?"):
        sg_key = getpass.getpass("  SendGrid API key: ").strip()
        sg_from = input("  Sender email address: ").strip()
        if sg_key and sg_from:
            env_lines.append(f"SENDGRID_API_KEY={sg_key}")
            env_lines.append(f"SENDGRID_FROM_EMAIL={sg_from}")
    print()

    # Canvas LMS
    if _ask_yes_no("Enable Canvas LMS for assignment deadlines?"):
        canvas_url = input("  Canvas URL (e.g. https://canvas.university.edu): ").strip()
        canvas_token = getpass.getpass("  Canvas API token: ").strip()
        if canvas_url and canvas_token:
            env_lines.append(f"CANVAS_BASE_URL={canvas_url}")
            env_lines.append(f"CANVAS_API_TOKEN={canvas_token}")
    print()

    # Step 5: Write .env file
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    env_path = project_root / ".env"

    if env_path.exists():
        overwrite = _ask_yes_no(f".env already exists at {env_path}. Overwrite?")
        if not overwrite:
            print("Setup cancelled. Your existing .env was not modified.")
            return

    env_content = "\n".join(env_lines) + "\n"
    env_path.write_text(env_content)

    print("=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print(f"\nConfiguration saved to: {env_path}")
    print("\nNext steps:")
    print("  1. Run: python -m secretary dry-run")
    print("     (This will test the connection and show what reminders would be sent)")
    print("  2. Run: python -m secretary run")
    print("     (This starts the daily scheduler)")
    print()

    # Count what's configured
    configured = []
    if gemini_key:
        configured.append("Gemini AI")
    configured.append("Google Calendar")
    if "GOOGLE_MAPS_API_KEY" in env_content:
        configured.append("Google Maps")
    if "TWILIO_ACCOUNT_SID" in env_content:
        configured.append("Twilio SMS")
    if "SENDGRID_API_KEY" in env_content:
        configured.append("SendGrid Email")
    if "CANVAS_API_TOKEN" in env_content:
        configured.append("Canvas LMS")

    print(f"Configured services: {', '.join(configured)}")
    print("You can re-run 'python -m secretary setup' anytime to reconfigure.")


def _ask_yes_no(question: str) -> bool:
    """Ask a yes/no question, default no."""
    answer = input(f"{question} [y/N]: ").strip().lower()
    return answer in ("y", "yes")
