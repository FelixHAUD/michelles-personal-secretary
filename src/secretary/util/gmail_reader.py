"""Gmail inbox reader — fetches unread/recent emails without Gemini."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from googleapiclient.discovery import build

from .google_auth import get_credentials

logger = logging.getLogger(__name__)


@dataclass
class EmailSummary:
    sender: str
    subject: str
    snippet: str
    date: str
    labels: list[str]


def fetch_recent_emails(
    credentials_path: str,
    hours: int = 24,
    max_results: int = 10,
) -> list[EmailSummary]:
    """Fetch recent emails from Gmail. No Gemini — just metadata."""
    try:
        creds = get_credentials(credentials_path)
        service = build("gmail", "v1", credentials=creds)

        # Only Primary inbox, unread, skip self-sent reminders
        query = (
            f"newer_than:{hours}h is:unread category:primary "
            f"-from:michellenguyen166@gmail.com"
        )

        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = results.get("messages", [])
        if not messages:
            return []

        summaries = []
        for msg_ref in messages:
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_ref["id"], format="metadata",
                         metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )

                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender_raw = headers.get("From", "Unknown")
                # Clean sender: "John Doe <john@example.com>" -> "John Doe"
                sender = sender_raw.split("<")[0].strip().strip('"')
                if not sender:
                    sender = sender_raw

                summaries.append(EmailSummary(
                    sender=sender,
                    subject=headers.get("Subject", "(No subject)"),
                    snippet=msg.get("snippet", ""),
                    date=headers.get("Date", ""),
                    labels=msg.get("labelIds", []),
                ))
            except Exception as e:
                logger.warning("Failed to fetch message %s: %s", msg_ref["id"], e)

        return summaries
    except Exception as e:
        logger.error("Gmail fetch failed: %s", e)
        return []


def format_email_digest(emails: list[EmailSummary]) -> str:
    """Format emails into a readable digest string."""
    if not emails:
        return "No important unread emails. Inbox looking clean!"

    lines = [f"{len(emails)} email(s) that need your attention:\n"]
    for em in emails:
        lines.append(f"{em.sender}")
        lines.append(f"  {em.subject}")
        lines.append("")

    return "\n".join(lines)
