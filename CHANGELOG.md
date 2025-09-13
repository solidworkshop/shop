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
