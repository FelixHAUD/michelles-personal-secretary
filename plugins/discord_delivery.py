"""Discord Webhook Delivery plugin — sends styled embeds to a Discord channel."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from secretary.plugin import ConfigRequirement, Delivery

logger = logging.getLogger(__name__)


# ── embed style lookup ──────────────────────────────────────────────
_STYLES: list[tuple[str, int, str]] = [
    # (substring to match in subject, embed colour, emoji prefix)
    ("Reminder:",       0x5865F2, "\U0001f697"),   # car — departure alert
    ("upcoming events", 0xFEE75C, "\u26a0\ufe0f"),  # warning — fallback
    ("Good Morning",    0x57F287, "\u2600\ufe0f"),   # sun — morning briefing
    ("Bedtime",         0x9B59B6, "\U0001f319"),     # moon — bedtime
]
_DEFAULT_COLOR = 0x5865F2
_DEFAULT_EMOJI = "\U0001f514"  # bell


def _pick_style(subject: str) -> tuple[int, str]:
    """Return (color, emoji) based on keywords found in *subject*."""
    for keyword, color, emoji in _STYLES:
        if keyword.lower() in subject.lower():
            return color, emoji
    return _DEFAULT_COLOR, _DEFAULT_EMOJI


def _body_to_fields(body: str) -> list[dict[str, str]]:
    """Split a multi-line body into Discord embed fields.

    Consecutive non-empty lines are grouped into a single field.  A blank
    line starts a new field.  If the body is short (one logical block) it
    is returned as a single field so the embed still looks clean.
    """
    fields: list[dict[str, str]] = []
    buffer: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            buffer.append(stripped)
        elif buffer:
            fields.append({
                "name": buffer[0],
                "value": "\n".join(buffer[1:]) if len(buffer) > 1 else "\u200b",
                "inline": False,
            })
            buffer = []

    # flush remaining lines
    if buffer:
        fields.append({
            "name": buffer[0],
            "value": "\n".join(buffer[1:]) if len(buffer) > 1 else "\u200b",
            "inline": False,
        })

    # If only one field was produced, put the whole body in the embed
    # description instead — cleaner for short messages.
    if len(fields) <= 1:
        return []

    return fields


class DiscordDelivery(Delivery):
    name = "discord"
    description = "Send reminders as styled embeds to a Discord channel via webhook"
    config_schema = [
        ConfigRequirement(
            key="DISCORD_WEBHOOK_URL",
            description="Full Discord webhook URL (https://discord.com/api/webhooks/...)",
            secret=True,
        ),
    ]

    # ── lifecycle ────────────────────────────────────────────────────
    def initialize(self, config: dict[str, Any]) -> None:
        self._webhook_url: str = config["DISCORD_WEBHOOK_URL"]
        logger.info("Discord delivery initialised (webhook configured)")

    # ── sending ──────────────────────────────────────────────────────
    def send(self, recipient: str, subject: str, body: str) -> bool:
        color, emoji = _pick_style(subject)
        title = f"{emoji}  {subject}"

        embed: dict[str, Any] = {
            "title": title,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Michelle's Personal Secretary"},
        }

        # Try to structure the body into fields; fall back to description.
        fields = _body_to_fields(body)
        if fields:
            embed["fields"] = fields
        else:
            embed["description"] = body

        payload: dict[str, Any] = {
            "embeds": [embed],
        }

        try:
            resp = requests.post(
                self._webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Discord reminder sent: %s", subject)
            return True
        except requests.RequestException:
            logger.exception("Failed to send Discord webhook for: %s", subject)
            return False

    # ── cleanup (no-op) ──────────────────────────────────────────────
    def cleanup(self, recipient: str) -> None:
        """No cleanup needed for Discord webhooks."""
        pass
