
# Shop + Pixel/CAPI Tester (v2.5.0)

**Restored rich Admin** (master channel switches, per-event toggles, QPS caps, concurrency, chaos, manual JSON with dry-run), plus Inspector, Logs, Catalog, live counters, and health checks. Public store pages included.

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
