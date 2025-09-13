# Demo Store + Meta Pixel & CAPI Tester — v1.4.0 (FULL)

**This ZIP contains ALL files** for the app (no partials).

## Render setup
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -k gthread -w 1 app:app`
- Env:
  - `PIXEL_ID`, `ACCESS_TOKEN`, `GRAPH_VER=v20.0`, `BASE_URL=https://your-app.onrender.com`
  - `TEST_EVENT_CODE` — leave blank for **live** Overview; fill to send to **Test Events** tab
  - `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`
  - `WEB_CONCURRENCY=1`

## If Events Manager shows no recent activity
1. In **/admin**, turn **off** “Use Test Event Code” (sends live events).
2. **/admin → Health → Show Config Summary** must show `pixel_id_present: true`, `access_token_present: true`.
3. Ensure `BASE_URL` domain is allowed under your Pixel’s **Allowed Domains** (for website action_source).
4. Click **Send Live Purchase Now** in Manual Send to force a live CAPI event.
5. Check **/admin → Logs** for responses. If you see `dry_run`, env vars are missing. If you see `http_400 2804050`, add more user_data (real browser will send cookies for fbp/fbc).

## Structure
- `app.py`, `config.py`, `extensions.py`, `models.py`
- `shop/` public routes + `/beacon` for client pixel simulation
- `admin/` full console (automation, chaos, counters, manual send, health, pixel check, logs, inspector)
- `templates/` pages with robots **noindex**
- `static/` includes `js/pixel.js`

