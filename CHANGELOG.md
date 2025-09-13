# Changelog

## v1.4.3
- Robust SQLite migration with product table rebuild if needed.
- Build badge v1.4.3.

## v1.4.4
- Fix SQLite migration transaction handling using `engine.begin()` (no nested BEGIN/COMMIT).
- Build badge v1.4.4.

## v1.4.5
- Add `/healthz` and `/health` endpoints that return HTTP 200 immediately (no DB).
- Build badge v1.4.5.

## v1.4.6
- Define `/healthz` and `/health` inside `create_app()` to avoid NameError during import.
- Build badge v1.4.6.

## v1.4.7
- Add global error handler (logs to EventLog) and 500.html page.
- Diagnostics: `/_diag/env`, `/_diag/db`.
- SQLite WAL mode + safer startup; engine pool pre-ping.
- Build badge v1.4.7.

## v1.4.8
- Bind Gunicorn to `$PORT` to satisfy Render routing (fixes 502 Bad Gateway).
- Build badge v1.4.8.

## v1.4.9
- Add global catch-all exception handler that logs to EventLog.
- Hardened shop routes to avoid 500s even if DB hiccups.
- Diagnostics: `/_diag/boot` shows last boot error.
- Build badge v1.4.9.

## v1.4.10
- Default SQLite path moved to `/var/tmp/app.db` (writable on Render).
- Added lock retry wrapper for create/commit operations.
- New `/_diag/dburi` to see effective DB URI.
- Build badge v1.4.10.

## v1.4.11
- Clean rewrite of app.py to resolve SyntaxError from prior patching.
- Keeps WAL, retries, diagnostics, and health endpoints.
- Build badge v1.4.11.

## v1.4.12
- Fix: global exception handler now **skips** `HTTPException` so redirects/404s work.
- Add `/admin/health` endpoint for quick admin readiness check.
- Build badge v1.4.12.
