"""Gmail SMTP Delivery plugin with auto-cleanup of old reminders."""

from __future__ import annotations

import email.utils
import imaplib
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any

from secretary.plugin import ConfigRequirement, Delivery

logger = logging.getLogger(__name__)

_REMINDER_SUBJECT_PREFIX = "Reminder:"


class GmailDelivery(Delivery):
    name = "gmail"
    description = "Send reminders to Gmail with auto-cleanup via IMAP"
    config_schema = [
        ConfigRequirement(key="SMTP_HOST", description="SMTP server, e.g. smtp.gmail.com"),
        ConfigRequirement(key="SMTP_PORT", description="SMTP port, e.g. 587"),
        ConfigRequirement(key="SMTP_USER", description="Gmail address"),
        ConfigRequirement(key="SMTP_PASSWORD", description="Gmail app password", secret=True),
        ConfigRequirement(
            key="REMINDER_TTL_HOURS",
            description="Hours before reminders are auto-deleted (default 2)",
            required=False,
        ),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        self._smtp_host = config["SMTP_HOST"]
        self._smtp_port = int(config["SMTP_PORT"])
        self._smtp_user = config["SMTP_USER"]
        self._smtp_password = config["SMTP_PASSWORD"]
        self._ttl_hours = int(config.get("REMINDER_TTL_HOURS", "2"))

    def send(self, recipient: str, subject: str, body: str) -> bool:
        # Clean up old reminders first
        self._cleanup_old_reminders(recipient)

        msg = MIMEText(body)
        msg["From"] = self._smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
            logger.info("Sent reminder email to %s: %s", recipient, subject)
            return True
        except Exception:
            logger.exception("Failed to send email to %s", recipient)
            return False

    def _cleanup_old_reminders(self, recipient: str) -> None:
        """Delete reminder emails older than TTL from the recipient's inbox via IMAP."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self._ttl_hours)
            cutoff_str = cutoff.strftime("%d-%b-%Y")

            imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            imap.login(self._smtp_user, self._smtp_password)
            imap.select("INBOX")

            # Search for old reminder emails from ourselves
            search_criteria = (
                f'(FROM "{self._smtp_user}" SUBJECT "{_REMINDER_SUBJECT_PREFIX}" '
                f'BEFORE {cutoff_str})'
            )
            status, msg_ids = imap.search(None, search_criteria)

            if status == "OK" and msg_ids[0]:
                ids = msg_ids[0].split()
                for mid in ids:
                    imap.store(mid, "+FLAGS", "\\Deleted")
                imap.expunge()
                logger.info("Cleaned up %d old reminder email(s)", len(ids))

            imap.close()
            imap.logout()
        except Exception:
            logger.debug("Reminder cleanup skipped: %s", exc_info=True)
