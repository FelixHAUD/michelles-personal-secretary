"""Daily scheduler using APScheduler."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from secretary.config import SecretaryConfig
from secretary.plugin import PluginRegistry

logger = logging.getLogger(__name__)


def start_scheduler(config: SecretaryConfig, registry: PluginRegistry) -> None:
    """Start the blocking scheduler that runs the pipeline on a cron schedule."""
    from .runner import run_pipeline

    scheduler = BlockingScheduler(timezone=config.user.timezone)

    trigger = CronTrigger.from_crontab(
        config.user.schedule_cron,
        timezone=config.user.timezone,
    )

    def job():
        logger.info("Scheduled run starting...")
        try:
            run_pipeline(config=config, registry=registry, dry_run=False)
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
    signal.signal(signal.SIGTERM, shutdown_handler)

    next_run = scheduler.get_jobs()[0].next_run_time if scheduler.get_jobs() else "unknown"
    print(f"Secretary scheduler started.")
    print(f"Schedule: {config.user.schedule_cron} ({config.user.timezone})")
    print(f"Next run: {next_run}")
    print(f"Press Ctrl+C to stop.\n")

    scheduler.start()
