"""SQLite-backed store that tracks which reminders have already been sent."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class DedupStore:
    """Tracks sent reminders so the pipeline never delivers the same one twice."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".secretary" / "secretary.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_reminders (
                fingerprint  TEXT PRIMARY KEY,
                event_id     TEXT,
                remind_at    TEXT,
                channel      TEXT,
                sent_at      TEXT,
                message_preview TEXT
            )
            """
        )
        self._conn.commit()

    def was_sent(self, fingerprint: str) -> bool:
        """Return True if this fingerprint has already been delivered."""
        row = self._conn.execute(
            "SELECT 1 FROM sent_reminders WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return row is not None

    def mark_sent(
        self,
        fingerprint: str,
        event_id: str,
        remind_at: str,
        channel: str,
        message_preview: str = "",
    ) -> None:
        """Record that a reminder was successfully sent."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO sent_reminders
                (fingerprint, event_id, remind_at, channel, sent_at, message_preview)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                event_id,
                remind_at,
                channel,
                datetime.now(timezone.utc).isoformat(),
                message_preview[:200],
            ),
        )
        self._conn.commit()

    def cleanup_old(self, days: int = 30) -> int:
        """Delete records older than *days*. Returns the number of rows removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM sent_reminders WHERE sent_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()
