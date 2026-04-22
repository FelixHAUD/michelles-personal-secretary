# Michelle's Personal Secretary

AI-powered personal secretary that fetches events from Google Calendar and Canvas LMS, analyzes them with Gemini, and delivers smart reminders to Discord.

**How it works:** fetch events → Gemini analyzes with tool-use (e.g. drive time, weather) → generates prioritized reminders → delivers via Discord with timed Cloud Tasks delivery.

## Prerequisites

- Python 3.12+
- [Gemini API key](https://aistudio.google.com/apikey) (free)
- Google Cloud project with **Calendar API** enabled and OAuth credentials downloaded as `credentials.json` ([guide](https://developers.google.com/calendar/api/quickstart/python))

Optional integrations (the app works without these — plugins auto-skip if unconfigured):

| Service | What it does |
|---------|-------------|
| Discord Webhook | Styled reminder embeds to a Discord channel |
| Open-Meteo Weather | Weather in briefings and departure alerts (free, no API key) |
| Twilio | SMS reminders |
| SMS Gateway | Email account (Gmail, etc.) — Free SMS via carrier email gateway |
| SendGrid | Email reminders |
| Google Maps | Drive time estimates in reminders |
| Canvas LMS | Assignment deadline reminders |

## Features

- Smart departure reminders with drive time + weather
- Morning briefing at 7 AM (schedule, weather, affirmation, study gaps)
- Gmail inbox digest at 8 AM (unread primary emails only)
- Weekly schedule overview (Sunday evening)
- Bedtime reminder at 11 PM with tomorrow preview
- Timed delivery via Cloud Tasks (reminders arrive at the right moment)
- Discord delivery with styled color-coded embeds
- Gemini fallback (plain event list when AI is unavailable)

## Google OAuth Setup

1. Create OAuth credentials in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) and download as `credentials.json`.
2. Enable the **Google Calendar API** and **Gmail API** (read-only) for your project.
3. On first run, a browser window opens for OAuth consent (Calendar + Gmail read access).
4. The resulting token is saved at `~/.secretary/token.json` for future runs.
5. For cloud deployment, the token is stored in **Secret Manager** (see Cloud Deployment below).

## Quick Start

```bash
git clone https://github.com/FelixHAUD/michelles-personal-secretary.git
cd michelles-personal-secretary
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
secretary setup
```

The setup wizard walks through all configuration interactively and writes a `.env` file.

On the first run that uses Google Calendar, a browser window opens for OAuth consent. The resulting token is saved as `token.json` for future runs.

## Usage

```bash
secretary dry-run        # Preview reminders without sending (default)
secretary run --once     # Single live run — fetches, analyzes, delivers
secretary run            # Start the daily scheduler (cron-based)
secretary test-plugins   # Validate all plugins load with current config
```

Add `-v` for debug logging: `secretary -v dry-run`

## Configuration

All settings live in `.env` (created by `secretary setup`, or copy `.env.example` manually).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Free at https://aistudio.google.com/apikey |
| `GOOGLE_CREDENTIALS_PATH` | Yes | `credentials.json` | Path to Google OAuth credentials JSON |
| `DISCORD_WEBHOOK_URL` | No | — | Discord webhook URL for delivery |
| `HOME_ADDRESS` | No | — | Home address for drive time calculations |
| `PHONE_NUMBER` | No | — | Phone number for SMS reminders |
| `EMAIL` | No | — | Email for email reminders |
| `TIMEZONE` | No | `America/Los_Angeles` | Scheduling timezone |
| `SCHEDULE_CRON` | No | `0 6 * * *` | Cron expression (default: 6 AM daily) |
| `LOOKAHEAD_HOURS` | No | `6` | How far ahead to scan for events (hours) |
| `TWILIO_ACCOUNT_SID` | No | — | Twilio SMS |
| `TWILIO_AUTH_TOKEN` | No | — | Twilio SMS |
| `TWILIO_FROM_NUMBER` | No | — | Twilio SMS |
| `SENDGRID_API_KEY` | No | — | SendGrid email |
| `SENDGRID_FROM_EMAIL` | No | — | SendGrid email |
| `SMTP_HOST` | No | — | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | No | — | SMTP port (e.g. `587`) |
| `SMTP_USER` | No | — | SMTP username (Gmail address) |
| `SMTP_PASSWORD` | No | — | SMTP password (Gmail app password) |
| `REMINDER_TTL_HOURS` | No | `2` | Hours before old reminder emails are auto-deleted from inbox |
| `SMS_GATEWAY_DOMAIN` | No | — | SMS gateway carrier domain (e.g. `txt.att.net`) — deprecated |
| `GOOGLE_MAPS_API_KEY` | No | — | Google Maps drive time |
| `CANVAS_API_TOKEN` | No | — | Canvas LMS |
| `CANVAS_BASE_URL` | No | — | Canvas LMS (e.g. `https://canvas.university.edu`) |

## Plugins

The app uses a plugin system. Drop a `.py` file in `plugins/` and it auto-registers on startup. See the existing plugins for examples:

- `google_calendar.py` — DataSource: fetches calendar events
- `canvas_lms.py` — DataSource: fetches assignment deadlines
- `google_maps.py` — Tool: drive time estimates (called by Gemini during analysis)
- `weather.py` — Tool: weather conditions and forecast (Open-Meteo, free)
- `discord_delivery.py` — Delivery: styled Discord embeds via webhook
- `gmail_delivery.py` — Delivery: email reminders via Gmail SMTP with IMAP auto-cleanup (optional, Discord is primary)
- `twilio_sms.py` — Delivery: sends SMS reminders
- `sms_gateway.py` — Delivery: free SMS via email-to-SMS carrier gateway (deprecated)
- `sendgrid_email.py` — Delivery: sends email reminders via SendGrid

Four plugin types are available (see `src/secretary/plugin/base.py`):

| Type | Purpose |
|------|---------|
| `DataSource` | Fetch events from external services |
| `Tool` | Provide tools the AI agent can call during reasoning |
| `Delivery` | Send reminders to the user |
| `Hook` | Transform data before or after the AI agent runs |

## Scheduling

`secretary run` starts a long-running process that fires the pipeline on a cron schedule. The machine must be on and the process running for reminders to fire. If the machine sleeps or shuts down, scheduled runs are missed. This still works for local development and testing.

For always-on reliability, use the Cloud Run deployment (see below).

## Cloud Deployment

Deployed to **Google Cloud Run** with timed reminder delivery via Cloud Tasks.

| Resource | Value |
|----------|-------|
| Service URL | `https://secretary-1070885118078.us-central1.run.app` |
| GCP project | `gen-lang-client-0243595792` |
| Region | `us-central1` |
| Cloud Tasks queue | `reminder-delivery` |

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/run` | AI-analyzed reminders via Gemini → schedules Cloud Tasks |
| `POST` | `/deliver` | Delivers a single reminder (called by Cloud Tasks) |
| `POST` | `/briefing` | Morning briefing: schedule + weather + study gaps + affirmation |
| `POST` | `/email-summary` | Unread primary email digest |
| `POST` | `/weekly` | 7-day schedule overview |
| `POST` | `/bedtime` | Bedtime reminder with tomorrow preview |
| `GET` | `/health` | Health check |

### Cloud Scheduler jobs

| Job | Schedule | Endpoint |
|-----|----------|----------|
| `secretary-trigger` | Every 6 hours | `/run` |
| `morning-briefing` | 7 AM PT daily | `/briefing` |
| `email-summary` | 8 AM PT daily | `/email-summary` |
| `bedtime-reminder` | 11 PM PT daily | `/bedtime` |
| `weekly-digest` | Sunday 8 PM PT | `/weekly` |

### How timed delivery works

`/run` analyzes upcoming events with Gemini, which decides when each reminder should fire (e.g., 30 min before class, drive-time minus buffer before work). For each reminder, a Cloud Task is scheduled at that `remind_at` time. When the task fires, it POSTs to `/deliver` to send the reminder.

### Security and secrets

- IAM-secured: `--no-allow-unauthenticated`, OIDC auth via `scheduler-invoker` service account
- Secrets (`credentials.json`, `token.json`) stored in **Secret Manager**, passed as env vars
- All other config passed as Cloud Run env vars

### Cloud-specific env vars

| Variable | Purpose |
|----------|---------|
| `PLUGINS_DIR` | Plugin discovery path (set to `/app/plugins` in Docker) |
| `GOOGLE_TOKEN_PATH` | OAuth token path (cloud writes secret to `/tmp/secrets/token.json`) |
| `GOOGLE_TOKEN_SECRET` | Secret Manager path for OAuth token persistence (cloud only) |

### Notes

- Gemini retry delay capped at 30s (Cloud Run has 300s request timeout)
- Cloud Scheduler and Cloud Tasks both use OIDC tokens from the `scheduler-invoker` service account
