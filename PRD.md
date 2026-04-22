# Product Requirements Document: Michelle's Personal Secretary

## Overview

Michelle's Personal Secretary is an AI-powered personal assistant that automates daily scheduling, reminders, and information delivery for a college student. It reads Michelle's Google Calendar and Gmail, uses Gemini AI to generate smart context-aware reminders, and delivers everything through Discord with styled, color-coded messages.

The system runs autonomously on Google Cloud Run with no manual intervention required.

## Problem Statement

College students juggle classes, work shifts, extracurriculars, assignments, and social events across multiple platforms. The mental overhead of tracking what's next, when to leave, what to bring, and what emails need attention leads to missed events, late arrivals, and unnecessary stress.

Michelle works shifts at Kaiser, takes physics/neuroscience/math classes at UCI, does tutoring, goes to CorePower Yoga and the gym, and manages a busy inbox. She needs a system that proactively tells her what she needs to know, when she needs to know it.

## Target User

- **Name**: Michelle
- **Profile**: UCI college student, part-time healthcare worker (Kaiser), active lifestyle
- **Devices**: Phone (primary), laptop (secondary)
- **Communication preference**: Discord (always open on phone)
- **Pain points**: Forgetting when to leave for events, missing emails, no consolidated view of the day ahead, no wind-down routine

## Features

### 1. Smart Departure Reminders
**What**: AI-analyzed reminders that tell Michelle exactly when to leave for each event, factoring in drive time from home and weather conditions.

**How it works**:
- Every 6 hours, the pipeline fetches upcoming Google Calendar events
- Gemini AI categorizes each event (work shift, class, exam, casual, etc.) and determines the optimal reminder time
- Google Maps API calculates real drive time from home
- Weather conditions are appended ("Bring an umbrella!")
- A Cloud Task is scheduled at the exact `remind_at` time
- At that moment, a styled Discord embed is delivered

**Event type rules**:
| Type | Priority | Remind At | Example |
|------|----------|-----------|---------|
| Work shifts | High | Start - drive time - 15 min | "Leave by 6:04 for Kaiser. Drive ~11 min." |
| Classes | Normal | Start - drive time - 10 min | "Leave by 1:20 for physics at EH 1200." |
| Exams | High | Immediately | "NEURO MIDTERM is today! Good luck." |
| Interviews | High | Start - 30 min | "Interview in 30 min. You've got this!" |
| Casual (gym, yoga) | Normal | Start - 30 min | "CorePower in 30 min." |
| Flights | High | Start - 2.5 hours | Packing reminder included |

**Fallback**: If Gemini is unavailable (rate limited, outage), a plain event list is sent so Michelle always receives something.

### 2. Morning Briefing
**What**: A consolidated daily digest delivered to Discord at 7:00 AM.

**Contains**:
- Positive affirmation message (rotated daily)
- Full day's schedule with times and locations
- Study gap detection (free windows > 1 hour between events)
- Current weather + forecast (temperature, conditions, rain chance)
- Contextual tips ("Bring an umbrella!", "Stay hydrated!")

**Delivery**: Green Discord embed with sun icon.

### 3. Email Digest
**What**: A summary of important unread emails delivered at 8:00 AM daily.

**Filters**:
- Unread only
- Primary inbox category only (excludes Promotions, Social, Updates tabs)
- Excludes self-sent emails (secretary's own reminders)
- Max 10 emails

**Shows**: Sender name + subject line for each email. No AI summarization needed.

**Delivery**: Bell icon Discord embed.

### 4. Weekly Digest
**What**: A 7-day schedule overview delivered Sunday at 8:00 PM.

**Contains**:
- Full schedule grouped by day
- Event count per day
- Busiest day / lightest day identification
- Free days highlighted (no events scheduled)

**Purpose**: Helps Michelle mentally prepare for the week and plan study time.

**Delivery**: Bell icon Discord embed.

### 5. Bedtime Reminder
**What**: A wind-down message delivered at 11:00 PM nightly.

**Contains**:
- Gentle "time to wind down" message
- Tomorrow's first event (time + title) so she can set an alarm if needed
- Rotating sleep tips (deep breathing, no screens, gratitude journaling)
- Goodnight message

**Delivery**: Purple Discord embed with moon icon.

## Architecture

### System Design
```
Google Calendar ──┐
                  ├── Pipeline ──> Gemini AI ──> Cloud Tasks ──> Discord
Gmail Inbox ──────┘       │                          │
                          │                     (timed delivery)
                    Google Maps                      │
                    Weather API                      ▼
                                              Discord Webhook
```

### Technology Stack
| Component | Technology | Cost |
|-----------|-----------|------|
| Runtime | Python 3.12 | Free |
| AI | Google Gemini 2.5 Flash | Free tier |
| Hosting | Google Cloud Run | Free tier |
| Scheduling | Cloud Scheduler (6 jobs) | Free tier (3 free + $0.10/job/mo) |
| Timed delivery | Cloud Tasks | Free tier |
| Calendar | Google Calendar API (OAuth) | Free |
| Email reading | Gmail API (OAuth) | Free |
| Drive time | Google Maps Directions API | Free tier |
| Weather | Open-Meteo API | Free, no key |
| Delivery | Discord Webhook | Free |
| Deduplication | SQLite (in-container) | Free |
| Secrets | Google Secret Manager | Free tier |

**Total monthly cost**: ~$0

### Plugin System
The app uses a plugin architecture. New features are added by dropping a `.py` file in the `plugins/` directory. Four plugin types:

- **DataSource** — Fetches events from external services (Google Calendar, Canvas LMS)
- **Tool** — Provides tools Gemini can call mid-analysis (Google Maps, Weather)
- **Delivery** — Sends messages to the user (Discord, Gmail, Twilio, SendGrid)
- **Hook** — Transforms data before/after the AI agent runs

Plugins auto-register on startup. A broken plugin doesn't prevent others from loading. Unconfigured plugins are silently skipped.

### Scheduled Jobs
| Job | Schedule | Endpoint | Uses AI? |
|-----|----------|----------|:--------:|
| secretary-trigger | Every 6h (midnight, 6AM, noon, 6PM PT) | /run | Yes (1 Gemini call) |
| morning-briefing | 7:00 AM PT daily | /briefing | No |
| email-summary | 8:00 AM PT daily | /email-summary | No |
| weekly-digest | Sunday 8:00 PM PT | /weekly | No |
| bedtime-reminder | 11:00 PM PT daily | /bedtime | No |

Only 1 of 5 scheduled jobs uses the Gemini API, minimizing free-tier quota consumption.

### Security
- Cloud Run: `--no-allow-unauthenticated` (OIDC auth required)
- All scheduler/task requests authenticated via `scheduler-invoker` service account
- OAuth tokens stored in Google Secret Manager
- Auto-refreshed tokens persisted back to Secret Manager
- Discord webhook URL stored as Cloud Run env var (not in code)

## Design Decisions

1. **Gemini over GPT/Claude**: $0 cost on free tier. Code is model-agnostic and can swap later.
2. **Discord over SMS/email**: Michelle always has Discord open. Rich embeds are more readable than plain text emails. Free, no carrier issues (AT&T killed email-to-SMS gateways in June 2025).
3. **Cloud Tasks for timed delivery**: Reminders arrive at the calculated moment (e.g., "leave by 1:30 PM") rather than being dumped in a batch every 6 hours.
4. **Zero-AI endpoints**: Morning briefing, email digest, weekly digest, and bedtime reminders use pure logic — no Gemini calls. This conserves the free tier quota for smart departure reminders where AI adds real value.
5. **Plugin architecture**: New features = new files. No core code changes needed. Distributable for other users to clone and customize.

## Current Limitations

- **Gemini free tier**: Rate limits can cause missed AI analysis in a cycle. Fallback covers this with a plain event list.
- **OAuth testing mode**: If the Google Cloud OAuth app is in "testing" status, refresh tokens expire after 7 days. Must publish to production to fix.
- **Single user**: Designed for Michelle. Multi-user support would require per-user config and OAuth tokens.
- **No inbound interaction**: Michelle can't reply to Discord messages to ask questions or give commands. The system is outbound-only.
- **Canvas LMS disabled**: Plugin exists but needs Michelle's Canvas API token and UCI's Canvas URL.
- **Static drive time origin**: All drive time calculations assume Michelle is at home. She may be on campus or elsewhere.

## Future Opportunities

### Near-term (single plugin each)
- **Smart drive time origin**: Infer Michelle's current location from her previous event's location instead of always assuming home. Pure prompt change — Gemini already has the full event list. Zero new APIs.
- **iPhone Shortcuts location webhook**: Michelle sets up a one-time iOS Shortcut that POSTs GPS coordinates to a `/location` endpoint. System stores latest coords (Firestore/Cloud Storage) and uses for drive time. Most accurate option.
- **Canvas LMS assignments**: "Physics problem set due in 14 hours" — plugin already built, just needs credentials
- **Commute alternatives**: Add transit/bus timing alongside drive time — minor tweak to Google Maps plugin
- **Study block suggestions**: Gemini suggests what to study in free gaps based on upcoming exams/deadlines

### Medium-term
- **Inbound Discord commands**: Michelle types "what's my schedule tomorrow?" and gets an answer — requires a Discord bot (not just webhook)
- **Expense tracking**: Reply to Discord with "spent $45 groceries" → logs to Google Sheet
- **Multi-calendar support**: Read from multiple Google Calendars (personal, school, work)

### Long-term
- **Multi-user SaaS**: Other students clone the repo and set up their own secretary
- **Voice integration**: "Hey secretary, when do I need to leave?" via Google Assistant or Alexa
- **Proactive suggestions**: "You have 3 exams next week — here's a suggested study schedule"
