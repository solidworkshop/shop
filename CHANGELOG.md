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
