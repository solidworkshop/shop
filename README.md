
# Shop + Pixel/CAPI Tester (v2.6.1)

Revert-style build + robust SQLite migration to avoid column-missing crashes on deploy. Full admin, 12 products, live counters, inspector, recent events, chaos, manual send, health checks.

## Env
SECRET_KEY=change-me
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
PIXEL_ID=
ACCESS_TOKEN=
GRAPH_VER=v18.0
TEST_EVENT_CODE=

## Render
Build: pip install -r requirements.txt
Start: gunicorn -k gthread -w 1 -b 0.0.0.0:$PORT app:app
Health: /healthz

## Diag
/diag returns build, env presence flags, and DB counts.
