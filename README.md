
# Shop + Pixel/CAPI Tester (v2.6.0)

"Revert-style" restore: rich admin, 12 products, working inspector, separate Manual Test, Recent Events panel, live counters.

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
