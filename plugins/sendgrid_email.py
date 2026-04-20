"""SendGrid Email Delivery plugin."""

from __future__ import annotations

from typing import Any

from secretary.plugin import ConfigRequirement, Delivery


class SendGridEmailDelivery(Delivery):
    name = "email"
    description = "Send email reminders via SendGrid"
    config_schema = [
        ConfigRequirement(key="SENDGRID_API_KEY", description="SendGrid API key", secret=True),
        ConfigRequirement(key="SENDGRID_FROM_EMAIL", description="Sender email address"),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        import sendgrid

        self._client = sendgrid.SendGridAPIClient(api_key=config["SENDGRID_API_KEY"])
        self._from = config["SENDGRID_FROM_EMAIL"]

    def send(self, recipient: str, subject: str, body: str) -> bool:
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=self._from,
            to_emails=recipient,
            subject=subject,
            plain_text_content=body,
        )
        response = self._client.send(message)
        return 200 <= response.status_code < 300
