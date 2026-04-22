# CLAUDE.md

AI secretary for Michelle. Fetches Google Calendar events (and Canvas LMS assignments), analyzes them with Gemini in a single batched call, and delivers smart reminders via Discord at the right time. Also runs several non-AI scheduled endpoints (briefing, bedtime, email summary, weekly digest).

## Tech stack

- Python 3.12
- Gemini 2.5 Flash (free tier, `google-genai` SDK) -- originally Anthropic/Opus, swapped for $0 cost
- Google Calendar API (OAuth 2.0, shared token with Gmail)
- Gmail API (OAuth 2.0, read-only -- used for email digest, not delivery)
- Google Maps API (drive time estimates)
- Open-Meteo API (weather, free, no API key)
- Discord webhook delivery (primary channel, styled embeds)
- Gmail SMTP delivery (disabled on Cloud Run -- SMTP env vars removed; still works locally)
- Flask + Gunicorn on Cloud Run
- Cloud Tasks for timed reminder delivery
- Cloud Scheduler for triggering pipeline runs and scheduled endpoints
- APScheduler (local mode only)
- SQLite dedup store

## Architecture rules

- **Plugin system**: new features = new `.py` file in `plugins/`. Four plugin types: `DataSource`, `Tool`, `Delivery`, `Hook`. Never touch core code if a plugin can do it.
- **Tech stack is locked**. Do not swap libraries or services without flagging to the user.
- **Batch all events in ONE Gemini call**. Never loop per-event.
- **Zero Gemini for non-AI endpoints**. `/briefing`, `/bedtime`, `/email-summary`, `/weekly` are pure logic. No Gemini calls.
- **Only /run calls Gemini** (once per cycle, max). Minimize Gemini calls -- free tier is limited.
- **Gemini fallback**: if AI analysis fails during `/run`, sends a plain event list to Discord so Michelle always gets something.
- **Read-only**: never modify external calendar/Canvas/Gmail data.
- **Current time passed to Gemini in user's local timezone** (not UTC) to prevent timezone mismatch in reminder scheduling.
- **Prompt tuning**: casual events (gym, tutoring) get reminders. Only truly flexible blocks (study hours) are skipped.
- **Drive time origin**: currently always HOME_ADDRESS. Planned: infer from previous event's location (prompt change only, no new APIs). Future option: iPhone Shortcuts webhook for real-time GPS → Firestore/Cloud Storage.
- **IMAP cleanup runs at end of every /run cycle** regardless of reminder count.
- **SMS gateways are dead**: AT&T killed email-to-SMS gateways June 2025. The `sms_gateway.py` plugin exists but is unused. Discord is the active delivery channel.

## Key paths

- `src/secretary/` -- core package
- `plugins/` -- auto-discovered plugin files (DataSource, Tool, Delivery, Hook)
- `cloud_run.py` -- Cloud Run Flask entry point (all HTTP endpoints)
- `src/secretary/agent/loop.py` -- Gemini agent with tool-use loop (max 10 rounds)
- `src/secretary/agent/prompt.py` -- system prompt builder
- `src/secretary/pipeline/runner.py` -- pipeline orchestrator (fetch -> agent -> deliver); `fetch_events()` extracted for reuse by non-AI endpoints
- `src/secretary/plugin/base.py` -- plugin ABCs
- `src/secretary/plugin/loader.py` -- plugin discovery (walks `plugins/` dir)
- `src/secretary/config/loader.py` -- config loading from `.env` and env vars
- `src/secretary/dedup/` -- SQLite deduplication store (`store.py`) and fingerprint hashing (`hasher.py`)
- `src/secretary/util/google_auth.py` -- shared Google OAuth with combined scopes (calendar.readonly + gmail.readonly). Handles token refresh + Secret Manager persistence. Both Calendar and Gmail plugins use this.
- `src/secretary/util/gmail_reader.py` -- Gmail inbox reader. Fetches unread primary emails (no Gemini). Filters: `is:unread`, `category:primary`, excludes self-sent. Max 10 results.
- `plugins/discord_delivery.py` -- Discord webhook delivery. Styled embeds by message type (green/sun for morning, purple/moon for bedtime, blue/car for departure, yellow/warning for fallback). Config: `DISCORD_WEBHOOK_URL`.
- `plugins/weather.py` -- Open-Meteo weather tool (free, no API key). Gemini can call `get_weather()` during analysis. Also called directly by `/briefing` endpoint. Uses Irvine CA coordinates by default.
- `Dockerfile` -- production image

## Development commands

```bash
pip install -e ".[dev]"          # Install locally with dev deps
secretary dry-run                # Preview reminders without sending
secretary run --once             # Single live run (fetches, analyzes, delivers)
secretary run                    # Start local scheduler (cron-based)
secretary test-plugins           # Validate all plugins load
python -m pytest tests/          # Run tests (101 tests)
```

Add `-v` for debug logging: `secretary -v dry-run`

## Cloud deployment

- **Deployment GCP project**: `gen-lang-client-0243595792`, region `us-central1`
- **OAuth credentials project**: `natural-broker-493907-t9` (different from deployment project; Gmail API enabled on both)
- **Cloud Run service**: `secretary`
  - URL: `https://secretary-1070885118078.us-central1.run.app`
  - IAM: `--no-allow-unauthenticated`
  - Gunicorn timeout: 300s

### Cloud Run endpoints

| Method | Path | Description | Uses Gemini |
|--------|------|-------------|-------------|
| POST/GET | `/run` | Main pipeline: fetch events, analyze with Gemini, schedule Cloud Tasks | Yes (once) |
| POST | `/deliver` | Deliver a single reminder (called by Cloud Tasks at remind_at time) | No |
| POST/GET | `/briefing` | Morning briefing: schedule + weather + study gaps + affirmation | No |
| POST/GET | `/bedtime` | Bedtime reminder with tomorrow preview + wind-down tips | No |
| POST/GET | `/email-summary` | Unread primary email digest (sender + subject) | No |
| POST/GET | `/weekly` | 7-day schedule overview with busiest/lightest day analysis | No |
| GET | `/health` | Health check | No |

### Cloud Scheduler jobs

| Job | Cron (America/Los_Angeles) | Endpoint |
|-----|---------------------------|----------|
| `secretary-trigger` | `0 */6 * * *` (every 6h) | `/run` |
| `morning-briefing` | `0 7 * * *` (7 AM daily) | `/briefing` |
| `email-summary` | `0 8 * * *` (8 AM daily) | `/email-summary` |
| `bedtime-reminder` | `0 23 * * *` (11 PM daily) | `/bedtime` |
| `weekly-digest` | `0 20 * * 0` (Sunday 8 PM) | `/weekly` |

### Cloud Tasks

- **Queue**: `reminder-delivery`
  - `/run` schedules tasks at each reminder's `remind_at` time
  - Tasks POST to `/deliver` to send the actual reminder

### Secrets and config

- **Secrets**: stored in Secret Manager (`google-credentials`, `google-token`), written to `/tmp/secrets/` at startup
- **Service account**: `scheduler-invoker` (Cloud Run Invoker role, used for OIDC on both Scheduler and Tasks)
- **Env vars in Docker**: `PLUGINS_DIR=/app/plugins`, `GOOGLE_TOKEN_PATH=/tmp/secrets/token.json`
- **Gmail SMTP delivery**: disabled on Cloud Run (SMTP env vars removed). Discord is primary delivery.
- **Gemini retry delay**: capped at 30s to fit Cloud Run's 300s request timeout

### Redeploy

```bash
gcloud builds submit --tag=us-central1-docker.pkg.dev/gen-lang-client-0243595792/secretary/secretary:latest
gcloud run deploy secretary --image=us-central1-docker.pkg.dev/gen-lang-client-0243595792/secretary/secretary:latest --region=us-central1
```

## Plugin system details

Plugins are `.py` files in `plugins/`. The loader (`src/secretary/plugin/loader.py`) walks the directory, imports each file, and finds all concrete `BasePlugin` subclasses. Files starting with `_` are skipped. A broken plugin file does not prevent others from loading.

Four plugin types (defined in `src/secretary/plugin/base.py`):

| Type | Purpose | Example |
|------|---------|---------|
| `DataSource` | Fetch events from external services | `google_calendar.py`, `canvas_lms.py` |
| `Tool` | Provide tools Gemini can call during analysis | `google_maps.py`, `weather.py` |
| `Delivery` | Send reminders to the user | `discord_delivery.py` (primary), `gmail_delivery.py` (local only), `twilio_sms.py`, `sendgrid_email.py`, `sms_gateway.py` |
| `Hook` | Transform data before/after the agent runs | (none currently) |

Each plugin declares a `config_schema` list of `ConfigRequirement` objects. The registry validates required keys are present during registration. Plugins auto-skip when unconfigured.

### Google OAuth

Shared OAuth via `src/secretary/util/google_auth.py`. Single token with combined scopes (`calendar.readonly` + `gmail.readonly`). Google Calendar plugin uses `google_auth.get_credentials()` instead of its own auth. Gmail reader also uses the shared token. Token refresh persists back to Secret Manager on Cloud Run.

## Pipeline flow (/run)

1. Fetch events from all `DataSource` plugins (`fetch_events()` is extracted and reused by non-AI endpoints)
2. Run `pre_agent` hooks
3. Send all events to Gemini in one call (with tool declarations from `Tool` plugins, current time in user's local timezone)
4. Gemini may call tools (e.g. Google Maps for drive time, weather) -- up to 10 rounds
5. Parse structured JSON response into `Reminder` and `Conflict` objects
6. Run `post_agent` hooks
7. Deliver via `Delivery` plugins (with SQLite dedup) or schedule via Cloud Tasks at each reminder's `remind_at` time
8. Run IMAP cleanup on all delivery plugins regardless of reminder count
- If Gemini fails at step 3-5, fallback sends a plain event list to Discord
