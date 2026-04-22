"""Cloud Run HTTP entry point.

Cloud Scheduler sends a POST to /run every 6 hours.
/run analyzes events and schedules Cloud Tasks at each reminder's remind_at time.
Cloud Tasks then POST to /deliver to send the actual reminder.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
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


@app.route("/run", methods=["POST", "GET"])
def run_handler():
    """Run the pipeline: fetch events, analyze with Gemini, schedule timed delivery."""
    from secretary.config import load_config
    from secretary.pipeline.runner import deliver_reminder, run_pipeline
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    # Analyze only — don't deliver yet
    try:
        output = run_pipeline(config=config, registry=registry, dry_run=True)
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 502

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
            except Exception as e:
                logger.warning("Cleanup failed for %s: %s", delivery.name, e)

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


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
