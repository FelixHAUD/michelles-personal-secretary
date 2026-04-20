"""Tests for the daily scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from secretary.config.schema import SecretaryConfig, UserConfig
from secretary.plugin import PluginRegistry


@pytest.fixture
def config():
    return SecretaryConfig(
        user=UserConfig(
            timezone="America/New_York",
            schedule_cron="30 7 * * *",
        ),
        gemini_api_key="fake-key",
    )


@pytest.fixture
def registry():
    return PluginRegistry()


@patch("secretary.pipeline.scheduler.BlockingScheduler")
def test_scheduler_uses_config_timezone(mock_scheduler_cls, config, registry):
    """BlockingScheduler is created with the timezone from config."""
    mock_scheduler = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.start.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        from secretary.pipeline.scheduler import start_scheduler

        start_scheduler(config=config, registry=registry)

    mock_scheduler_cls.assert_called_once_with(timezone="America/New_York")


@patch("secretary.pipeline.scheduler.CronTrigger")
@patch("secretary.pipeline.scheduler.BlockingScheduler")
def test_cron_trigger_from_config(mock_scheduler_cls, mock_cron_cls, config, registry):
    """CronTrigger is created from config.user.schedule_cron."""
    mock_scheduler = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.start.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        from secretary.pipeline.scheduler import start_scheduler

        start_scheduler(config=config, registry=registry)

    mock_cron_cls.from_crontab.assert_called_once_with(
        "30 7 * * *",
        timezone="America/New_York",
    )


@patch("secretary.pipeline.scheduler.CronTrigger")
@patch("secretary.pipeline.scheduler.BlockingScheduler")
def test_job_has_misfire_grace_time(mock_scheduler_cls, mock_cron_cls, config, registry):
    """Job is added with misfire_grace_time=3600."""
    mock_scheduler = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.start.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        from secretary.pipeline.scheduler import start_scheduler

        start_scheduler(config=config, registry=registry)

    mock_scheduler.add_job.assert_called_once()
    call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs.kwargs["id"] == "daily_secretary"
    assert call_kwargs.kwargs["misfire_grace_time"] == 3600


@patch("secretary.pipeline.scheduler.CronTrigger")
@patch("secretary.pipeline.scheduler.BlockingScheduler")
def test_scheduler_start_is_called(mock_scheduler_cls, mock_cron_cls, config, registry):
    """scheduler.start() is called to begin blocking execution."""
    mock_scheduler = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.start.return_value = None

    from secretary.pipeline.scheduler import start_scheduler

    start_scheduler(config=config, registry=registry)

    mock_scheduler.start.assert_called_once()
