"""Tests for the interactive setup wizard."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from secretary.config.wizard import run_wizard, _ask_yes_no


class TestRunWizard:
    """Test run_wizard writes .env with correct content based on user input."""

    def test_full_setup_with_all_integrations(self, tmp_path, monkeypatch):
        """All fields filled in, all optional integrations enabled."""
        inputs = iter([
            # Core settings
            "123 Main St, City, ST 12345",  # home address
            "+15551234567",                  # phone
            "user@example.com",              # email
            "America/New_York",              # timezone
            "30 7 * * *",                    # cron
            # Google Calendar
            "/path/to/credentials.json",     # creds path
            # Optional integrations
            "y",                             # enable Google Maps
            "y",                             # enable Twilio
            "ACtest123",                     # Twilio SID
            "+15559876543",                  # Twilio from number
            "y",                             # enable SendGrid
            "sender@example.com",            # SendGrid from email
            "y",                             # enable Canvas
            "https://canvas.university.edu", # Canvas URL
        ])
        getpass_inputs = iter([
            "AIza-test-gemini-key",  # Gemini API key
            "maps-api-key-123",      # Maps API key
            "twilio-auth-token",     # Twilio auth token
            "SG.sendgrid-key",       # SendGrid API key
            "canvas-token-abc",      # Canvas API token
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        # Point project_root resolution to tmp_path
        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()

        assert "HOME_ADDRESS=123 Main St, City, ST 12345" in content
        assert "PHONE_NUMBER=+15551234567" in content
        assert "EMAIL=user@example.com" in content
        assert "TIMEZONE=America/New_York" in content
        assert "SCHEDULE_CRON=30 7 * * *" in content
        assert "GEMINI_API_KEY=AIza-test-gemini-key" in content
        assert "GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json" in content
        assert "GOOGLE_MAPS_API_KEY=maps-api-key-123" in content
        assert "TWILIO_ACCOUNT_SID=ACtest123" in content
        assert "TWILIO_AUTH_TOKEN=twilio-auth-token" in content
        assert "TWILIO_FROM_NUMBER=+15559876543" in content
        assert "SENDGRID_API_KEY=SG.sendgrid-key" in content
        assert "SENDGRID_FROM_EMAIL=sender@example.com" in content
        assert "CANVAS_BASE_URL=https://canvas.university.edu" in content
        assert "CANVAS_API_TOKEN=canvas-token-abc" in content

    def test_defaults_used_when_enter_pressed(self, tmp_path, monkeypatch):
        """Pressing Enter for optional fields uses defaults."""
        inputs = iter([
            "",                  # home address (skip)
            "",                  # phone (skip)
            "",                  # email (skip)
            "",                  # timezone (default)
            "",                  # cron (default)
            "",                  # creds path (default)
            "n",                 # no Google Maps
            "n",                 # no Twilio
            "n",                 # no SendGrid
            "n",                 # no Canvas
        ])
        getpass_inputs = iter([
            "test-gemini-key",   # Gemini API key
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()

        # Defaults applied
        assert "TIMEZONE=America/Los_Angeles" in content
        assert "SCHEDULE_CRON=0 6 * * *" in content
        assert "GOOGLE_CREDENTIALS_PATH=credentials.json" in content
        assert "GEMINI_API_KEY=test-gemini-key" in content

        # Skipped fields not present
        assert "HOME_ADDRESS" not in content
        assert "PHONE_NUMBER" not in content
        assert "EMAIL=" not in content
        assert "GOOGLE_MAPS_API_KEY" not in content
        assert "TWILIO_ACCOUNT_SID" not in content
        assert "SENDGRID_API_KEY" not in content
        assert "CANVAS_API_TOKEN" not in content

    def test_skips_optional_integrations_when_user_says_no(self, tmp_path, monkeypatch):
        """Saying 'n' to optional integrations excludes them from .env."""
        inputs = iter([
            "456 Elm St",        # home
            "",                  # phone (skip)
            "",                  # email (skip)
            "",                  # timezone (default)
            "",                  # cron (default)
            "",                  # creds path (default)
            "n",                 # no Google Maps
            "n",                 # no Twilio
            "n",                 # no SendGrid
            "n",                 # no Canvas
        ])
        getpass_inputs = iter([
            "gemini-key",        # Gemini API key
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        env_path = tmp_path / ".env"
        content = env_path.read_text()

        assert "HOME_ADDRESS=456 Elm St" in content
        assert "GEMINI_API_KEY=gemini-key" in content
        assert "GOOGLE_MAPS_API_KEY" not in content
        assert "TWILIO" not in content
        assert "SENDGRID" not in content
        assert "CANVAS" not in content

    def test_does_not_overwrite_existing_env_when_declined(self, tmp_path, monkeypatch):
        """If .env exists and user says no to overwrite, file is unchanged."""
        env_path = tmp_path / ".env"
        original_content = "GEMINI_API_KEY=original-key\n"
        env_path.write_text(original_content)

        inputs = iter([
            "",                  # home (skip)
            "",                  # phone (skip)
            "",                  # email (skip)
            "",                  # timezone (default)
            "",                  # cron (default)
            "",                  # creds path (default)
            "n",                 # no Google Maps
            "n",                 # no Twilio
            "n",                 # no SendGrid
            "n",                 # no Canvas
            "n",                 # do NOT overwrite existing .env
        ])
        getpass_inputs = iter([
            "new-gemini-key",    # Gemini API key
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        assert env_path.read_text() == original_content

    def test_overwrites_existing_env_when_confirmed(self, tmp_path, monkeypatch):
        """If .env exists and user says yes, file is replaced."""
        env_path = tmp_path / ".env"
        env_path.write_text("GEMINI_API_KEY=old-key\n")

        inputs = iter([
            "",                  # home (skip)
            "",                  # phone (skip)
            "",                  # email (skip)
            "",                  # timezone (default)
            "",                  # cron (default)
            "",                  # creds path (default)
            "n",                 # no Google Maps
            "n",                 # no Twilio
            "n",                 # no SendGrid
            "n",                 # no Canvas
            "y",                 # YES overwrite existing .env
        ])
        getpass_inputs = iter([
            "new-gemini-key",    # Gemini API key
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        content = env_path.read_text()
        assert "GEMINI_API_KEY=new-gemini-key" in content
        assert "old-key" not in content

    def test_gemini_warning_when_key_empty(self, tmp_path, monkeypatch, capsys):
        """Warns when no Gemini key is provided."""
        inputs = iter([
            "",                  # home (skip)
            "",                  # phone (skip)
            "",                  # email (skip)
            "",                  # timezone (default)
            "",                  # cron (default)
            "",                  # creds path (default)
            "n",                 # no Google Maps
            "n",                 # no Twilio
            "n",                 # no SendGrid
            "n",                 # no Canvas
        ])
        getpass_inputs = iter([
            "",                  # empty Gemini key
        ])

        monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
        monkeypatch.setattr("secretary.config.wizard.getpass.getpass", lambda _prompt="": next(getpass_inputs))

        fake_wizard_path = tmp_path / "src" / "secretary" / "config" / "wizard.py"
        fake_wizard_path.parent.mkdir(parents=True)
        fake_wizard_path.touch()
        import secretary.config.wizard as wizard_mod
        monkeypatch.setattr(wizard_mod, "__file__", str(fake_wizard_path))

        run_wizard()

        captured = capsys.readouterr()
        assert "Warning: Gemini API key is required" in captured.out


class TestAskYesNo:
    """Test the _ask_yes_no helper."""

    @pytest.mark.parametrize("answer,expected", [
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("YES", True),
        ("n", False),
        ("N", False),
        ("no", False),
        ("", False),
        ("maybe", False),
    ])
    def test_yes_no_responses(self, answer, expected, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _prompt="": answer)
        assert _ask_yes_no("Test?") == expected
