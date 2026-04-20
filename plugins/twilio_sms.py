"""Twilio SMS Delivery plugin."""

from __future__ import annotations

from typing import Any

from secretary.plugin import ConfigRequirement, Delivery


class TwilioSMSDelivery(Delivery):
    name = "sms"
    description = "Send SMS reminders via Twilio"
    config_schema = [
        ConfigRequirement(key="TWILIO_ACCOUNT_SID", description="Twilio Account SID", secret=True),
        ConfigRequirement(key="TWILIO_AUTH_TOKEN", description="Twilio Auth Token", secret=True),
        ConfigRequirement(key="TWILIO_FROM_NUMBER", description="Twilio phone number"),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        from twilio.rest import Client

        self._client = Client(config["TWILIO_ACCOUNT_SID"], config["TWILIO_AUTH_TOKEN"])
        self._from = config["TWILIO_FROM_NUMBER"]

    def send(self, recipient: str, subject: str, body: str) -> bool:
        message = self._client.messages.create(
            body=f"{subject}\n\n{body}",
            from_=self._from,
            to=recipient,
        )
        return message.sid is not None
