
# Shop + Pixel/CAPI Tester (v2.0.0)

**Complete** Flask app:
- Public shop: home, product detail, cart, checkout, about, FAQ, contact (unique product URLs)
- Meta Pixel (front-end) + Conversions API (server) with **all standard events** via automation & manual send
- Robots.txt and `X-Robots-Tag` noindex
- Admin (Flask-Login) with: Automation controls, Counters (Pixel/CAPI/Deduped, Margin events, PLTV events), Chaos toggles,
  Request Inspector (last N payloads), Logs, Health/Pixel check, and **Catalog** editor (cost + HTML description)
- SQLite persistence at `/var/tmp/app.db`

## .env (Render)
```
SECRET_KEY=change-me
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
PIXEL_ID=1234567890
ACCESS_TOKEN=your_graph_token
GRAPH_VER=v18.0
TEST_EVENT_CODE=TEST123
BASE_URL=https://your-domain.onrender.com
```

## Build / Run (Render)
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -k gthread -w 1 -b 0.0.0.0:$PORT app:app`
- Health check: `/healthz`

## Notes
- **Counters** for Margin/PLTV show count of **events** that include those fields (not sums).
- Automation emits a mix of PageView and Purchase with seeded randomness and optional chaos.
- Use **Manual JSON** input on dashboard to post raw payloads to CAPI (with dedup `event_id`).

