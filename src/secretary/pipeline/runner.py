"""Pipeline orchestrator — fetch events, run agent, deliver reminders."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from secretary.agent import Event, generate_reminders
from secretary.agent.types import AgentOutput, Reminder
from secretary.config import SecretaryConfig
from secretary.dedup import DedupStore, reminder_fingerprint
from secretary.plugin import PluginRegistry

logger = logging.getLogger(__name__)


def run_pipeline(
    config: SecretaryConfig,
    registry: PluginRegistry,
    dry_run: bool = False,
) -> AgentOutput:
    """Run the full pipeline: fetch -> agent -> print/deliver.

    Returns the AgentOutput so callers (e.g. the scheduler) can schedule
    individual reminder deliveries at their remind_at times.
    """

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=config.user.lookahead_hours)

    # Step 1: Fetch events from all data sources (error-isolated)
    all_events: list[Event] = []
    for source in registry.data_sources:
        try:
            raw_events = source.fetch_events(now, end)
            for raw in raw_events:
                all_events.append(
                    Event(
                        event_id=raw["event_id"],
                        title=raw["title"],
                        start=datetime.fromisoformat(raw["start"]),
                        end=datetime.fromisoformat(raw["end"]),
                        location=raw.get("location", ""),
                        description=raw.get("description", ""),
                        source=raw.get("source", source.name),
                    )
                )
            logger.info("%s: fetched %d events", source.name, len(raw_events))
        except Exception as e:
            logger.error("%s failed: %s", source.name, e)

    print(f"Found {len(all_events)} upcoming events.\n")

    empty = AgentOutput(reminders=[], conflicts=[])

    if not all_events:
        print(f"No events in the next {config.user.lookahead_hours} hours. Nothing to do.")
        return empty

    # Step 2: Show what we fetched
    for event in all_events:
        loc = f" @ {event.location}" if event.location else ""
        print(f"  - {event.title}{loc}")
        print(f"    {event.start.strftime('%a %b %d, %I:%M %p')} - {event.end.strftime('%I:%M %p')}")
    print()

    # Step 3: Run pre-agent hooks
    for hook in registry.hooks.get("pre_agent", []):
        try:
            all_events = hook.process(all_events)
        except Exception as e:
            logger.error("Pre-agent hook %s failed: %s", hook.name, e)

    # Step 4: Send to agent
    print("Analyzing events with Gemini...")
    output = generate_reminders(
        events=all_events,
        api_key=config.gemini_api_key,
        home_address=config.user.home_address,
        registry=registry,
    )

    # Step 5: Run post-agent hooks
    for hook in registry.hooks.get("post_agent", []):
        try:
            output = hook.process(output)
        except Exception as e:
            logger.error("Post-agent hook %s failed: %s", hook.name, e)

    # Step 6: Print results
    _print_output(output)

    # Step 7: Deliver with dedup (only for immediate delivery modes)
    if not dry_run and registry.deliveries:
        for r in output.reminders:
            deliver_reminder(config, registry, r)

    return output


def deliver_reminder(
    config: SecretaryConfig,
    registry: PluginRegistry,
    reminder: Reminder,
) -> None:
    """Deliver a single reminder through all configured delivery channels."""
    dedup = DedupStore()
    remind_at_iso = reminder.remind_at.isoformat()

    for delivery in registry.deliveries:
        fp = reminder_fingerprint(reminder.event_id, remind_at_iso, delivery.name)
        if dedup.was_sent(fp):
            logger.info(
                "Skipping duplicate: %s via %s", reminder.event_title, delivery.name
            )
            continue
        try:
            recipient = (
                config.user.phone_number
                if delivery.name in ("sms", "sms_gateway")
                else config.user.email
            )
            success = delivery.send(
                recipient=recipient,
                subject=f"Reminder: {reminder.event_title}",
                body=reminder.message,
            )
            if success:
                dedup.mark_sent(
                    fp, reminder.event_id, remind_at_iso, delivery.name, reminder.message
                )
                logger.info(
                    "Delivered: %s via %s", reminder.event_title, delivery.name
                )
        except Exception as e:
            logger.error("Delivery %s failed: %s", delivery.name, e)

    dedup.cleanup_old()
    dedup.close()


def _print_output(output: AgentOutput) -> None:
    """Print reminders and conflicts to console."""
    if output.reminders:
        print(f"\n{'='*60}")
        print(f"  REMINDERS ({len(output.reminders)})")
        print(f"{'='*60}\n")
        for r in sorted(output.reminders, key=lambda x: x.remind_at):
            priority_marker = "!" if r.priority == "high" else " "
            print(f"  [{priority_marker}] {r.event_title}")
            print(f"      When: {r.remind_at.strftime('%a %b %d, %I:%M %p')}")
            print(f"      {r.message}")
            print()

    if output.conflicts:
        print(f"{'='*60}")
        print(f"  CONFLICTS ({len(output.conflicts)})")
        print(f"{'='*60}\n")
        for c in output.conflicts:
            print(f"  !! {c.description}")
            print()

    if not output.reminders and not output.conflicts:
        print("\nNo reminders or conflicts to report.")
