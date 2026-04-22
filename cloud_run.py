"""Cloud Run HTTP entry point.

Cloud Scheduler sends a POST to /run every 6 hours.
/run analyzes events and schedules Cloud Tasks at each reminder's remind_at time.
Cloud Tasks then POST to /deliver to send the actual reminder.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def _write_secret_files() -> None:
    """Write Google OAuth JSON from env vars to files (for Cloud Run)."""
    secrets_dir = Path("/tmp/secrets")
    secrets_dir.mkdir(exist_ok=True)

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        path = secrets_dir / "credentials.json"
        path.write_text(creds_json)
        os.environ.setdefault("GOOGLE_CREDENTIALS_PATH", str(path))

    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_json:
        path = secrets_dir / "token.json"
        path.write_text(token_json)
        os.environ.setdefault("GOOGLE_TOKEN_PATH", str(path))


_write_secret_files()

app = Flask(__name__)

# Cloud Tasks config (set via env vars on Cloud Run)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "gen-lang-client-0243595792")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
TASKS_QUEUE = os.environ.get("TASKS_QUEUE", "reminder-delivery")
SERVICE_URL = os.environ.get("SERVICE_URL", "")
INVOKER_SA = os.environ.get(
    "INVOKER_SA",
    f"scheduler-invoker@{GCP_PROJECT}.iam.gserviceaccount.com",
)


def _schedule_task(reminder_payload: dict, schedule_time: datetime) -> str:
    """Create a Cloud Tasks task to deliver a reminder at schedule_time."""
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(GCP_PROJECT, GCP_LOCATION, TASKS_QUEUE)

    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(schedule_time)

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{SERVICE_URL}/deliver",
            headers={"Content-Type": "application/json"},
            body=json.dumps(reminder_payload).encode(),
            oidc_token=tasks_v2.OidcToken(
                service_account_email=INVOKER_SA,
                audience=SERVICE_URL,
            ),
        ),
        schedule_time=ts,
    )

    created = client.create_task(parent=parent, task=task)
    return created.name


def _send_fallback_email(config, registry, events, error: str) -> bool:
    """When Gemini fails, send a plain event summary so Michelle always gets something."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(config.user.timezone)
    lines = ["Your AI secretary couldn't analyze events right now, "
             "but here's what's coming up:\n"]
    for e in sorted(events, key=lambda x: x.start):
        start_local = e.start.astimezone(tz)
        loc = f" @ {e.location}" if e.location else ""
        lines.append(f"  {start_local.strftime('%I:%M %p')} - {e.title}{loc}")

    lines.append(f"\n(AI analysis failed: {error[:100]})")
    body = "\n".join(lines)

    for delivery in registry.deliveries:
        try:
            delivery.send(
                recipient=config.user.email,
                subject="Your upcoming events",
                body=body,
            )
            logger.info("Sent fallback event summary via %s", delivery.name)
            return True
        except Exception as ex:
            logger.error("Fallback delivery via %s failed: %s", delivery.name, ex)
    return False


@app.route("/run", methods=["POST", "GET"])
def run_handler():
    """Run the pipeline: fetch events, analyze with Gemini, schedule timed delivery."""
    from secretary.config import load_config
    from secretary.pipeline.runner import (
        deliver_reminder,
        fetch_events,
        run_pipeline,
    )
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    # Fetch events first so we can fall back if Gemini fails
    events = fetch_events(config, registry)

    # Analyze with Gemini — pass pre-fetched events
    try:
        output = run_pipeline(
            config=config, registry=registry, dry_run=True, events=events,
        )
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        fallback_sent = False
        if events:
            fallback_sent = _send_fallback_email(config, registry, events, str(e))
        return jsonify({
            "status": "fallback" if fallback_sent else "error",
            "error": str(e),
            "fallback_sent": fallback_sent,
            "events_found": len(events),
        }), 200 if fallback_sent else 502

    now = datetime.now(timezone.utc)
    scheduled = 0
    delivered_now = 0

    for r in output.reminders:
        if r.remind_at <= now:
            # Past due — deliver immediately
            deliver_reminder(config, registry, r)
            delivered_now += 1
        else:
            payload = {
                "event_id": r.event_id,
                "event_title": r.event_title,
                "remind_at": r.remind_at.isoformat(),
                "message": r.message,
                "priority": r.priority,
            }
            task_name = _schedule_task(payload, r.remind_at)
            logger.info("Scheduled task %s for %s at %s", task_name, r.event_title, r.remind_at)
            scheduled += 1

    # Always clean up old reminder emails, even if no new reminders this cycle
    for delivery in registry.deliveries:
        if hasattr(delivery, "cleanup"):
            try:
                delivery.cleanup(config.user.email)
            except Exception as ex:
                logger.warning("Cleanup failed for %s: %s", delivery.name, ex)

    return jsonify({
        "status": "ok",
        "reminders_analyzed": len(output.reminders),
        "delivered_now": delivered_now,
        "scheduled": scheduled,
        "conflicts_found": len(output.conflicts),
    })


@app.route("/deliver", methods=["POST"])
def deliver_handler():
    """Deliver a single reminder (called by Cloud Tasks at the remind_at time)."""
    from secretary.agent.types import Reminder
    from secretary.config import load_config
    from secretary.pipeline.runner import deliver_reminder
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)

    data = request.get_json(force=True)
    reminder = Reminder(
        event_id=data["event_id"],
        event_title=data["event_title"],
        remind_at=datetime.fromisoformat(data["remind_at"]),
        message=data["message"],
        priority=data.get("priority", "normal"),
    )

    config = load_config()
    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    deliver_reminder(config, registry, reminder)
    logger.info("Delivered: %s", reminder.event_title)

    return jsonify({"status": "delivered", "event_title": reminder.event_title})


AFFIRMATIONS = [
    "You're doing amazing — one step at a time.",
    "Today is full of possibilities. You've got this!",
    "You are capable of incredible things.",
    "Be proud of how far you've come.",
    "You're stronger than you think.",
    "Small progress is still progress. Keep going!",
    "Believe in yourself — you've earned everything you have.",
    "Today is a new chance to be the best version of you.",
    "Hard work always pays off. You're proof of that.",
    "The world is better because you're in it.",
    "Trust the process. Great things take time.",
    "You are enough, exactly as you are.",
    "Every expert was once a beginner. Keep learning!",
    "Your potential is limitless.",
    "Breathe. You're exactly where you need to be.",
]


@app.route("/briefing", methods=["POST", "GET"])
def briefing_handler():
    """Morning briefing: today's schedule, weather, and an affirmation."""
    import random
    from zoneinfo import ZoneInfo

    from secretary.config import load_config
    from secretary.pipeline.runner import fetch_events
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    tz = ZoneInfo(config.user.timezone)
    now_local = datetime.now(tz)
    day_name = now_local.strftime("%A, %B %d")

    # Fetch today's events (use 18h lookahead for full day view)
    from secretary.config.schema import SecretaryConfig
    day_config = SecretaryConfig(
        user=config.user,
        gemini_api_key=config.gemini_api_key,
        google_credentials_path=config.google_credentials_path,
        env=config.env,
    )
    day_config.user.lookahead_hours = 18
    events = fetch_events(day_config, registry)
    events.sort(key=lambda e: e.start)

    # Weather
    try:
        from plugins.weather import get_weather
        weather = get_weather()
    except Exception:
        weather = "Weather unavailable."

    # Build briefing
    affirmation = random.choice(AFFIRMATIONS)

    if events:
        schedule_lines = []
        for e in events:
            start_local = e.start.astimezone(tz)
            loc = f" @ {e.location}" if e.location else ""
            schedule_lines.append(
                f"  {start_local.strftime('%I:%M %p')} — {e.title}{loc}"
            )
        schedule_text = "\n".join(schedule_lines)
    else:
        schedule_text = "  Nothing on the calendar — enjoy your free day!"

    # Study gaps — find windows > 1h between events
    gap_lines = []
    if len(events) >= 2:
        for i in range(len(events) - 1):
            gap_start = events[i].end.astimezone(tz)
            gap_end = events[i + 1].start.astimezone(tz)
            gap_hours = (gap_end - gap_start).total_seconds() / 3600
            if gap_hours >= 1:
                gap_lines.append(
                    f"  {gap_start.strftime('%I:%M %p')} — {gap_end.strftime('%I:%M %p')} "
                    f"({gap_hours:.0f}h free between {events[i].title} and {events[i+1].title})"
                )

    gap_text = ""
    if gap_lines:
        gap_text = "\n\nStudy Windows:\n" + "\n".join(gap_lines)

    body = (
        f"Good Morning, Michelle!\n\n"
        f"{affirmation}\n\n"
        f"Here's your {day_name}:\n\n"
        f"{schedule_text}{gap_text}\n\n"
        f"Weather: {weather}"
    )

    for delivery in registry.deliveries:
        try:
            delivery.send(
                recipient=config.user.email,
                subject="Good Morning, Michelle!",
                body=body,
            )
            logger.info("Sent morning briefing via %s", delivery.name)
        except Exception as ex:
            logger.error("Briefing delivery via %s failed: %s", delivery.name, ex)

    return jsonify({
        "status": "ok",
        "events_today": len(events),
        "weather": weather,
    })


@app.route("/bedtime", methods=["POST", "GET"])
def bedtime_handler():
    """11 PM bedtime reminder."""
    import random
    from zoneinfo import ZoneInfo

    from secretary.config import load_config
    from secretary.pipeline.runner import fetch_events
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    tz = ZoneInfo(config.user.timezone)
    tomorrow = (datetime.now(tz) + timedelta(days=1))

    # Peek at tomorrow's first event
    from secretary.config.schema import SecretaryConfig
    tmrw_config = SecretaryConfig(
        user=config.user,
        gemini_api_key=config.gemini_api_key,
        google_credentials_path=config.google_credentials_path,
        env=config.env,
    )
    tmrw_config.user.lookahead_hours = 18
    events = fetch_events(tmrw_config, registry)
    events.sort(key=lambda e: e.start)

    if events:
        first = events[0]
        first_time = first.start.astimezone(tz).strftime("%I:%M %p")
        tomorrow_peek = f"Your first thing tomorrow is {first.title} at {first_time}."
    else:
        tomorrow_peek = "Nothing on the calendar tomorrow morning — sleep in if you can!"

    tips = [
        "Put your phone on Do Not Disturb.",
        "Try some deep breaths — in for 4, hold for 7, out for 8.",
        "No screens for the next 30 min if you can!",
        "A glass of water now will help you feel great in the morning.",
        "Write down one thing you're grateful for today.",
    ]

    body = (
        f"Hey Michelle, it's time to wind down.\n\n"
        f"{tomorrow_peek}\n\n"
        f"Tip: {random.choice(tips)}\n\n"
        f"Get some rest — you deserve it. Goodnight!"
    )

    for delivery in registry.deliveries:
        try:
            delivery.send(
                recipient=config.user.email,
                subject="Bedtime Reminder",
                body=body,
            )
            logger.info("Sent bedtime reminder via %s", delivery.name)
        except Exception as ex:
            logger.error("Bedtime delivery via %s failed: %s", delivery.name, ex)

    return jsonify({"status": "ok", "tomorrow_first_event": events[0].title if events else None})


@app.route("/email-summary", methods=["POST", "GET"])
def email_summary_handler():
    """Daily email digest — lists recent emails without Gemini."""
    from secretary.config import load_config
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.gmail_reader import fetch_recent_emails, format_email_digest
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    emails = fetch_recent_emails(config.google_credentials_path, hours=24)
    body = format_email_digest(emails)

    for delivery in registry.deliveries:
        try:
            delivery.send(
                recipient=config.user.email,
                subject="Daily Email Summary",
                body=body,
            )
            logger.info("Sent email summary via %s", delivery.name)
        except Exception as ex:
            logger.error("Email summary delivery via %s failed: %s", delivery.name, ex)

    return jsonify({"status": "ok", "emails_found": len(emails)})


@app.route("/weekly", methods=["POST", "GET"])
def weekly_handler():
    """Weekly digest — 7-day schedule overview. No Gemini, pure calendar math."""
    from collections import defaultdict
    from zoneinfo import ZoneInfo

    from secretary.config import load_config
    from secretary.config.schema import SecretaryConfig
    from secretary.pipeline.runner import fetch_events
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    tz = ZoneInfo(config.user.timezone)

    # Fetch next 7 days of events
    week_config = SecretaryConfig(
        user=config.user,
        gemini_api_key=config.gemini_api_key,
        google_credentials_path=config.google_credentials_path,
        env=config.env,
    )
    week_config.user.lookahead_hours = 168  # 7 days
    events = fetch_events(week_config, registry)
    events.sort(key=lambda e: e.start)

    # Group by day
    by_day: dict[str, list] = defaultdict(list)
    for e in events:
        day_key = e.start.astimezone(tz).strftime("%A, %b %d")
        by_day[day_key].append(e)

    # Build digest
    lines = ["Here's your week ahead:\n"]

    if not events:
        lines.append("Nothing scheduled — wide open week!")
    else:
        busiest_day = max(by_day.items(), key=lambda x: len(x[1]))
        lightest_day = min(by_day.items(), key=lambda x: len(x[1]))

        for day_name, day_events in by_day.items():
            lines.append(f"{day_name} ({len(day_events)} event{'s' if len(day_events) != 1 else ''}):")
            for e in day_events:
                start_local = e.start.astimezone(tz)
                loc = f" @ {e.location}" if e.location else ""
                lines.append(f"  {start_local.strftime('%I:%M %p')} — {e.title}{loc}")
            lines.append("")

        lines.append(f"Busiest day: {busiest_day[0]} ({len(busiest_day[1])} events)")
        if len(lightest_day[1]) < len(busiest_day[1]):
            lines.append(f"Lightest day: {lightest_day[0]} ({len(lightest_day[1])} events)")

        # Find days with no events in the next 7 days
        now_local = datetime.now(tz)
        all_days = set()
        for i in range(7):
            d = now_local + timedelta(days=i)
            all_days.add(d.strftime("%A, %b %d"))
        free_days = all_days - set(by_day.keys())
        if free_days:
            lines.append(f"Free days: {', '.join(sorted(free_days))}")

    body = "\n".join(lines)

    for delivery in registry.deliveries:
        try:
            delivery.send(
                recipient=config.user.email,
                subject="Your Week Ahead",
                body=body,
            )
            logger.info("Sent weekly digest via %s", delivery.name)
        except Exception as ex:
            logger.error("Weekly digest delivery via %s failed: %s", delivery.name, ex)

    return jsonify({"status": "ok", "events_this_week": len(events), "days_with_events": len(by_day)})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
