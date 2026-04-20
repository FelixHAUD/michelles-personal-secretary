"""Tests for delivery plugins — Twilio SMS and SendGrid email."""

import sys
from unittest.mock import MagicMock

import pytest

from secretary.plugin import PluginRegistry

# ---------------------------------------------------------------------------
# Stub out third-party SDK modules so tests run without them installed.
# ---------------------------------------------------------------------------
_twilio_rest = MagicMock()
_twilio = MagicMock()
_twilio.rest = _twilio_rest
sys.modules.setdefault("twilio", _twilio)
sys.modules.setdefault("twilio.rest", _twilio_rest)

_sendgrid = MagicMock()
_sendgrid_helpers = MagicMock()
_sendgrid_helpers_mail = MagicMock()
_sendgrid.helpers = _sendgrid_helpers
_sendgrid.helpers.mail = _sendgrid_helpers_mail
sys.modules.setdefault("sendgrid", _sendgrid)
sys.modules.setdefault("sendgrid.helpers", _sendgrid_helpers)
sys.modules.setdefault("sendgrid.helpers.mail", _sendgrid_helpers_mail)

from plugins.twilio_sms import TwilioSMSDelivery  # noqa: E402
from plugins.sendgrid_email import SendGridEmailDelivery  # noqa: E402


class TestTwilioSMSDelivery:
    def test_send_calls_twilio_correctly(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM12345"
        mock_client.messages.create.return_value = mock_message
        _twilio_rest.Client.return_value = mock_client

        plugin = TwilioSMSDelivery()
        plugin.initialize({
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_FROM_NUMBER": "+15550001111",
        })

        result = plugin.send("+15559999999", "Test Subject", "Test body")

        assert result is True
        mock_client.messages.create.assert_called_once_with(
            body="Test Subject\n\nTest body",
            from_="+15550001111",
            to="+15559999999",
        )

    def test_send_returns_false_when_sid_is_none(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = None
        mock_client.messages.create.return_value = mock_message
        _twilio_rest.Client.return_value = mock_client

        plugin = TwilioSMSDelivery()
        plugin.initialize({
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_FROM_NUMBER": "+15550001111",
        })

        result = plugin.send("+15559999999", "Subject", "Body")
        assert result is False

    def test_registry_skips_when_config_missing(self):
        registry = PluginRegistry()
        registry.register(TwilioSMSDelivery, {})
        assert len(registry.deliveries) == 0
        assert len(registry._failed) == 1
        assert "Missing config" in registry._failed[0][1]


class TestSendGridEmailDelivery:
    def test_send_calls_sendgrid_correctly(self):
        mock_sg_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_sg_client.send.return_value = mock_response
        _sendgrid.SendGridAPIClient.return_value = mock_sg_client

        mock_mail_obj = MagicMock()
        _sendgrid_helpers_mail.Mail.return_value = mock_mail_obj

        plugin = SendGridEmailDelivery()
        plugin.initialize({
            "SENDGRID_API_KEY": "SG.test",
            "SENDGRID_FROM_EMAIL": "from@example.com",
        })

        result = plugin.send("to@example.com", "Test Subject", "Test body")

        assert result is True
        _sendgrid_helpers_mail.Mail.assert_called_with(
            from_email="from@example.com",
            to_emails="to@example.com",
            subject="Test Subject",
            plain_text_content="Test body",
        )
        mock_sg_client.send.assert_called_once_with(mock_mail_obj)

    def test_send_returns_false_on_failure_status(self):
        mock_sg_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_sg_client.send.return_value = mock_response
        _sendgrid.SendGridAPIClient.return_value = mock_sg_client

        plugin = SendGridEmailDelivery()
        plugin.initialize({
            "SENDGRID_API_KEY": "SG.test",
            "SENDGRID_FROM_EMAIL": "from@example.com",
        })

        result = plugin.send("to@example.com", "Subject", "Body")
        assert result is False

    def test_registry_skips_when_config_missing(self):
        registry = PluginRegistry()
        registry.register(SendGridEmailDelivery, {})
        assert len(registry.deliveries) == 0
        assert len(registry._failed) == 1
        assert "Missing config" in registry._failed[0][1]
