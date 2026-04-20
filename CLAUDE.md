# CLAUDE.md

AI secretary for Michelle. Fetches Google Calendar events (and Canvas LMS assignments), analyzes them with Gemini in a single batched call, and delivers smart reminders via Gmail at the right time.

## Tech stack

- Python 3.12
- Gemini 2.5 Flash (free tier, `google-genai` SDK) -- originally Anthropic/Opus, swapped for $0 cost
- Google Calendar API (OAuth 2.0)
- Google Maps API (drive time estimates)
- Gmail SMTP delivery (active channel)
- Flask + Gunicorn on Cloud Run
- Cloud Tasks for timed reminder delivery
- Cloud Scheduler for triggering pipeline runs
- APScheduler (local mode only)
- SQLite dedup store

## Architecture rules

- **Plugin system**: new features = new `.py` file in `plugins/`. Four plugin types: `DataSource`, `Tool`, `Delivery`, `Hook`. Never touch core code if a plugin can do it.
- **Tech stack is locked**. Do not swap libraries or services without flagging to the user.
- **Batch all events in ONE Gemini call**. Never loop per-event.
- **Read-only**: never modify external calendar/Canvas data.
- **SMS gateways are dead**: AT&T killed email-to-SMS gateways June 2025. The `sms_gateway.py` plugin exists but is unused. Gmail is the active delivery channel.

## Key paths

- `src/secretary/` -- core package
- `plugins/` -- auto-discovered plugin files (DataSource, Tool, Delivery, Hook)
- `cloud_run.py` -- Cloud Run Flask entry point (`/run`, `/deliver`, `/health`)
- `src/secretary/agent/loop.py` -- Gemini agent with tool-use loop (max 10 rounds)
- `src/secretary/agent/prompt.py` -- system prompt builder
- `src/secretary/pipeline/runner.py` -- pipeline orchestrator (fetch -> agent -> deliver)
- `src/secretary/plugin/base.py` -- plugin ABCs
- `src/secretary/plugin/loader.py` -- plugin discovery (walks `plugins/` dir)
- `src/secretary/config/loader.py` -- config loading from `.env` and env vars
- `src/secretary/dedup.py` -- SQLite deduplication store
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

- **GCP project**: `gen-lang-client-0243595792`, region `us-central1`
- **Cloud Run service**: `secretary`
  - URL: `https://secretary-1070885118078.us-central1.run.app`
  - IAM: `--no-allow-unauthenticated`
  - Gunicorn timeout: 300s
- **Cloud Scheduler**: `secretary-trigger`, cron `0 */6 * * *` (every 6h, LA timezone)
  - POSTs to `/run` which analyzes events and schedules Cloud Tasks
- **Cloud Tasks queue**: `reminder-delivery`
  - `/run` schedules tasks at each reminder's `remind_at` time
  - Tasks POST to `/deliver` to send the actual email
- **Secrets**: stored in Secret Manager (`google-credentials`, `google-token`), written to `/tmp/secrets/` at startup
- **Service account**: `scheduler-invoker` (Cloud Run Invoker role, used for OIDC on both Scheduler and Tasks)
- **Env vars in Docker**: `PLUGINS_DIR=/app/plugins`, `GOOGLE_TOKEN_PATH=/tmp/secrets/token.json`
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
| `Tool` | Provide tools Gemini can call during analysis | `google_maps.py` |
| `Delivery` | Send reminders to the user | `gmail_delivery.py`, `twilio_sms.py` |
| `Hook` | Transform data before/after the agent runs | (none currently) |

Each plugin has a `name` attribute and an `enabled(env)` classmethod that checks whether required config is present. Plugins auto-skip when unconfigured.

## Pipeline flow

1. Fetch events from all `DataSource` plugins
2. Run `pre_agent` hooks
3. Send all events to Gemini in one call (with tool declarations from `Tool` plugins)
4. Gemini may call tools (e.g. Google Maps for drive time) -- up to 10 rounds
5. Parse structured JSON response into `Reminder` and `Conflict` objects
6. Run `post_agent` hooks
7. Deliver via `Delivery` plugins (with SQLite dedup) or schedule via Cloud Tasks
