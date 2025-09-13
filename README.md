# Demo Store + Meta Pixel & CAPI Tester — v1.4.14 (FULL)

See CHANGELOG for details. Deploy on Render with the provided commands and env vars.


## Render notes
- **Start Command** must be: `gunicorn -k gthread -w 1 -b 0.0.0.0:$PORT app:app`
- **Health Check Path**: `/healthz`
- Set `WEB_CONCURRENCY=1` and keep free plan resource limits in mind.
