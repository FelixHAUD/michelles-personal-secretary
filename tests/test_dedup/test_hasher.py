"""Tests for reminder fingerprint generation."""

from secretary.dedup.hasher import reminder_fingerprint


class TestReminderFingerprint:
    def test_deterministic(self):
        fp1 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        fp2 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        assert fp1 == fp2

    def test_different_event_ids(self):
        fp1 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        fp2 = reminder_fingerprint("evt_2", "2026-04-21T09:00:00+00:00", "sms")
        assert fp1 != fp2

    def test_different_remind_at(self):
        fp1 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        fp2 = reminder_fingerprint("evt_1", "2026-04-21T10:00:00+00:00", "sms")
        assert fp1 != fp2

    def test_different_channels(self):
        fp1 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        fp2 = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "email")
        assert fp1 != fp2

    def test_length_is_16_hex(self):
        fp = reminder_fingerprint("evt_1", "2026-04-21T09:00:00+00:00", "sms")
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)
