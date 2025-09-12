# Store Simulator: Meta Pixel + CAPI Test Shop

A modular Flask app that simulates a realistic online store and doubles as a Meta Pixel + CAPI testing tool, with automation, rate limiting, chaos toggles, payload validator hooks, EMQ practice counters, request inspector, and a password‑protected admin console backed by SQLite.

## Features
- Realistic shop: home, product, cart, checkout, about, FAQ, contact.
- Meta standard events fired (simulated Pixel client-side logging + server-side CAPI calls).
- robots.txt + meta noindex.
- Admin (Flask-Login): master switches, per-event toggles, raw JSON send, automation with configurable presets, global stop, QPS caps per channel, counters, logs, request inspector, health/version panel.
- Purchase-only extras: Margin = (price − random cost%), PLTV (fixed or randomized).
- Chaos toggles: drop events, omit params, malformed values.
- Seeded randomness (extend via KVStore seed if desired).
- Catalog manager with editable items and multicurrency.
- SQLite persistence for logs and settings.

## Quickstart
1. **Create and fill `.env`** (see `.env.example`).
2. **Create a virtualenv** and install deps:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Run**:
   ```bash
   python app.py
   ```
4. Visit `http://127.0.0.1:5000/` (shop) and `http://127.0.0.1:5000/admin` (console).

> If `PIXEL_ID`/`ACCESS_TOKEN` are not set, CAPI runs in **dry_run** mode and still logs payloads.

## Admin Login
- Username/password sourced from `.env` (`ADMIN_USER`, `ADMIN_PASS`).

## Graph API / Test Events
- Set `GRAPH_VER` and `TEST_EVENT_CODE` in `.env`. When configured, server-side CAPI forwards to Graph with your token. Otherwise, it stays in **dry_run** and logs locally.

## Robots & Noindex
- Served via `/robots.txt` (Disallow all) and `<meta name="robots" content="noindex">` in base template, plus `X-Robots-Tag` header.

## Persistence
- SQLite DB lives at `sqlite:///store.db` (configurable via `DATABASE_URL`).

## Scripts & Automation
- Admin → Automation: start/stop preset runners. Rate limiting uses simple token buckets per channel.

## EMQ Practice Hooks
- Payload construction is centralized in `admin.routes:make_event`. Extend to count coverage per parameter and surface in the dashboard.

## Requirements
Create **requirements.txt**:
```
Flask==3.0.3
python-dotenv==1.0.1
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Migrate==4.0.7
requests==2.32.3
Werkzeug==3.0.3
```
(Already included in ZIP.)

## Environment (.env)
```
FLASK_SECRET_KEY=change-me
ADMIN_USER=admin
ADMIN_PASS=change-me

PIXEL_ID=
ACCESS_TOKEN=
GRAPH_VER=v20.0
TEST_EVENT_CODE=

BASE_URL=http://127.0.0.1:5000

AUTOMATION_MAX_CONCURRENCY=4
RATE_LIMIT_QPS_PIXEL=5
RATE_LIMIT_QPS_CAPI=5
BUILD_NUMBER=v1.0.0
```

## Notes
- This baseline follows your spec while staying readable. You can extend automation presets, add per-event interval UIs, seed controls, chaos toggles UI, diff viewer, and a Pixel install checker (fetch `/` and scan for Pixel snippet if you later embed one) without breaking structure.
- Nothing is removed silently—future updates should append to `CHANGELOG.md`.


## v1.0.1 Additions
- Chaos toggles UI (drop, omit, malformed)
- Seed control for deterministic runs
- Per-event interval inputs; automation uses saved intervals
- Pixel install checker button (verifies snippet presence and noindex)
- **JS pixel snippet** (`static/js/pixel.js`) auto-fires PageView (respecting toggles) and exposes `window.demoPixel()`,
  plus **/pixel-collect** route to log test beacons as Pixel events.
