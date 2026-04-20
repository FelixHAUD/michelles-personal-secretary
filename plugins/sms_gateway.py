"""Email-to-SMS gateway Delivery plugin (free alternative to Twilio)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any

from secretary.plugin import ConfigRequirement, Delivery

logger = logging.getLogger(__name__)


class SMSGatewayDelivery(Delivery):
    name = "sms_gateway"
    description = "Send SMS via email-to-SMS carrier gateway (free)"
    config_schema = [
        ConfigRequirement(key="SMS_GATEWAY_DOMAIN", description="Carrier gateway domain, e.g. txt.att.net"),
        ConfigRequirement(key="SMTP_HOST", description="SMTP server, e.g. smtp.gmail.com"),
        ConfigRequirement(key="SMTP_PORT", description="SMTP port"),
        ConfigRequirement(key="SMTP_USER", description="SMTP login email"),
        ConfigRequirement(key="SMTP_PASSWORD", description="SMTP app password", secret=True),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        self._gateway_domain = config["SMS_GATEWAY_DOMAIN"]
        self._smtp_host = config["SMTP_HOST"]
        self._smtp_port = int(config["SMTP_PORT"])
        self._smtp_user = config["SMTP_USER"]
        self._smtp_password = config["SMTP_PASSWORD"]

    def send(self, recipient: str, subject: str, body: str) -> bool:
        number = recipient.lstrip("+")
        if number.startswith("1"):
            number = number[1:]
        gateway_email = f"{number}@{self._gateway_domain}"

        msg = MIMEText(f"{subject}\n\n{body}")
        msg["From"] = self._smtp_user
        msg["To"] = gateway_email
        msg["Subject"] = subject

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("Failed to send SMS via gateway to %s", gateway_email)
            return False
