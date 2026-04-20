"""Tests for the SQLite-backed dedup store."""

from datetime import datetime, timedelta, timezone

import pytest

from secretary.dedup.store import DedupStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = DedupStore(db_path)
    yield s
    s.close()


class TestDedupStore:
    def test_was_sent_returns_false_initially(self, store):
        assert store.was_sent("abc123") is False

    def test_mark_sent_then_was_sent(self, store):
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", "Test msg")
        assert store.was_sent("fp1") is True

    def test_different_fingerprint_not_found(self, store):
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", "Test msg")
        assert store.was_sent("fp2") is False

    def test_mark_sent_is_idempotent(self, store):
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", "Test msg")
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", "Test msg")
        assert store.was_sent("fp1") is True

    def test_cleanup_old_removes_expired(self, store):
        # Manually insert a record with an old sent_at timestamp
        old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        store._conn.execute(
            "INSERT INTO sent_reminders (fingerprint, event_id, remind_at, channel, sent_at, message_preview) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("old_fp", "evt_old", "2026-01-01T00:00:00+00:00", "sms", old_time, "old"),
        )
        store._conn.commit()

        assert store.was_sent("old_fp") is True
        removed = store.cleanup_old(days=30)
        assert removed == 1
        assert store.was_sent("old_fp") is False

    def test_cleanup_old_keeps_recent(self, store):
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", "recent")
        removed = store.cleanup_old(days=30)
        assert removed == 0
        assert store.was_sent("fp1") is True

    def test_message_preview_truncated(self, store):
        long_msg = "x" * 500
        store.mark_sent("fp1", "evt_1", "2026-04-21T09:00:00+00:00", "sms", long_msg)
        row = store._conn.execute(
            "SELECT message_preview FROM sent_reminders WHERE fingerprint = ?",
            ("fp1",),
        ).fetchone()
        assert len(row[0]) == 200
