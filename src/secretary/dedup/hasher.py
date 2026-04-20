"""Fingerprint generation for reminder deduplication."""

from __future__ import annotations

import hashlib


def reminder_fingerprint(event_id: str, remind_at: str, channel: str) -> str:
    """Produce a short hash that uniquely identifies a reminder delivery attempt."""
    raw = f"{event_id}|{remind_at}|{channel}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
