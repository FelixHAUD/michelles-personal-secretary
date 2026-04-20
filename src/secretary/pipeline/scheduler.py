"""Daily scheduler using APScheduler."""

from __future__ import annotations

import atexit
import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from secretary.config import SecretaryConfig
from secretary.plugin import PluginRegistry

logger = logging.getLogger(__name__)


def start_scheduler(config: SecretaryConfig, registry: PluginRegistry) -> None:
    """Start the blocking scheduler that runs the pipeline on a cron schedule."""
    from .runner import deliver_reminder, run_pipeline

    scheduler = BlockingScheduler(timezone=config.user.timezone)

    trigger = CronTrigger.from_crontab(
        config.user.schedule_cron,
        timezone=config.user.timezone,
    )

    def job():
        logger.info("Scheduled run starting...")
        try:
            # Run pipeline without immediate delivery (dry_run=True skips delivery)
            output = run_pipeline(config=config, registry=registry, dry_run=True)

            # Schedule each reminder at its remind_at time
            now = datetime.now(timezone.utc)
            scheduled = 0
            for r in output.reminders:
                if r.remind_at <= now:
                    # Past due — deliver immediately
                    logger.info("Delivering now (past due): %s", r.event_title)
                    deliver_reminder(config, registry, r)
                else:
                    # Schedule for the future
                    scheduler.add_job(
                        deliver_reminder,
                        trigger=DateTrigger(run_date=r.remind_at),
                        args=[config, registry, r],
                        id=f"reminder_{r.event_id}_{r.remind_at.isoformat()}",
                        name=f"Reminder: {r.event_title}",
                        misfire_grace_time=900,
                        replace_existing=True,
                    )
                    logger.info(
                        "Scheduled: %s at %s",
                        r.event_title,
                        r.remind_at.strftime("%a %b %d, %I:%M %p"),
                    )
                    scheduled += 1

            print(f"\nScheduled {scheduled} reminder(s) for timed delivery.")
        except Exception as e:
            logger.error("Pipeline run failed: %s", e)
        logger.info(
            "Scheduled run complete. Next run at: %s",
            scheduler.get_job("daily_secretary").next_run_time,
        )

    scheduler.add_job(
        job,
        trigger=trigger,
        id="daily_secretary",
        name="Daily Secretary Run",
        misfire_grace_time=3600,
    )

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received, stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)

    if sys.platform == "win32":
        # Windows doesn't deliver SIGTERM from external sources (taskkill, etc.).
        # Register SIGBREAK (Ctrl+Break / taskkill without /F) and an atexit
        # handler so the scheduler shuts down cleanly on Windows.
        signal.signal(signal.SIGBREAK, shutdown_handler)
        atexit.register(lambda: scheduler.shutdown(wait=False))
    else:
        signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        jobs = scheduler.get_jobs()
        next_run = getattr(jobs[0], "next_run_time", None) if jobs else None
        next_run = next_run or "unknown"
    except Exception:
        next_run = "unknown"
    print(f"Secretary scheduler started.")
    print(f"Schedule: {config.user.schedule_cron} ({config.user.timezone})")
    print(f"Next run: {next_run}")
    print(f"Press Ctrl+C to stop.\n")

    scheduler.start()
